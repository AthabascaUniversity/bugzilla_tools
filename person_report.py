#!/usr/bin/python

import sys
import os
import MySQLdb
import argparse
import datetime,time
import ConfigParser
import numpy

# select userid from profiles where login_name='X@athabascau.ca';
# userid
# ------
# 137
# ------
# select distinct(bug_id) from longdescs where who=137;
# select distinct(bug_id) from bugs_activity where who=137;

class PersonInfo:
    login_name=None
    userid=None
    realname=None

def loadDBInfo(config_file):
    bdbi={}
    bugzillarc=ConfigParser.ConfigParser()
    bugzillarc.read(config_file)
    defaults=bugzillarc.defaults()

    bdbi=defaults
    bdbi['port']=int(defaults['port'])
    return bdbi

def getPersonInfo(bdb,login_name):
    pi=PersonInfo()
    pi.login_name=login_name
    c=bdb.cursor()
    c.execute('select userid,realname from profiles where login_name=%s',(login_name))
    while(True):
        row=c.fetchone()
        if row == None:
            break
        (pi.userid,pi.realname)=row
    return pi

def getBugList(bdb,pi):
    """Get list of bugs person was ever associated with"""
    bug_ids=set()
    userid=pi.userid

    cld=bdb.cursor()
    # cld.execute('select distinct(bug_id) from longdescs as l,  where who=%s',(userid))
    cld.execute("""select distinct(l.bug_id),b.short_desc,unix_timestamp(b.creation_ts),
                          unix_timestamp(b.delta_ts),b.reporter,b.assigned_to,b.bug_status,b.resolution 
                     from longdescs as l, bugs as b 
                     where l.who=%s and l.bug_id=b.bug_id""",(userid))
    while (True):
        ldrow=cld.fetchone()
        if ldrow == None:
            break
        bug_ids.add((ldrow[0],ldrow[1],ldrow[2],ldrow[3],ldrow[4],ldrow[5],ldrow[6],ldrow[7]))

    cba=bdb.cursor()
    cba.execute("""select distinct(ba.bug_id),b.short_desc,unix_timestamp(b.creation_ts),
                          unix_timestamp(b.delta_ts),b.reporter,b.assigned_to,b.bug_status,b.resolution 
                     from bugs_activity as ba, bugs as b 
                     where (ba.who=%s or ba.added=%s or ba.removed=%s) and ba.bug_id=b.bug_id""",(userid,pi.login_name,pi.login_name))
    while (True):
        barow=cba.fetchone()
        if ldrow == None:
            break
        bug_ids.add((barow[0],barow[1]),barow[2],barow[3],barow[4],barow[5],barow[6],barow[7])

    bug_list=list(bug_ids)
    bug_list.sort()
    print "DEBUG: Number of bugs: ", len(bug_list)
    return bug_list

def getEventList(bdb,bug_list,full_report=True):
    """Get list of bugs person was ever associated with"""
    def append_event(el,etype,bug_id,event):
        if not el.has_key(bug_id):
            el[bug_id]=[]
        el[bug_id].append({'type':etype,'event':event})

    event_list={}
    now=time.mktime(datetime.datetime.now().timetuple())
    # userid=pi.userid

    for (bug,bug_desc,creation_ts,delta_ts,reporter,assigned_to,bug_status,resolution) in bug_list:
        c=bdb.cursor()
        c.execute("""select ba.who,unix_timestamp(ba.bug_when),ba.added,ba.removed,f.fieldid,f.name 
                       from bugs_activity ba, fielddefs f
                       where ba.bug_id=%s and f.fieldid=ba.fieldid order by ba.bug_when""",(bug))
        bug_events=[]
        while(True):
            row=c.fetchone()
            if row == None:
                break
            (who,bug_when,added,removed,fieldid,fieldname)=row
            bug_events.append({'type':'bugs_activity','field':(fieldname,fieldid),'event':(who,bug_when,added,removed)})

        c=bdb.cursor()
        c.execute("""select l.who,unix_timestamp(l.bug_when),l.thetext,f.fieldid,f.name 
                       from longdescs as l, fielddefs f
                       where l.bug_id=%s and f.name='longdesc' order by bug_when""",(bug))

        while(True):
            row=c.fetchone()
            if row == None:
                break
            (who,bug_when,added,fieldid,fieldname)=row
            bug_events.append({'type':'longdescs','field':(fieldname,fieldid),'event':(who,bug_when,added,None)})

        bug_events.append({'type':'creation_ts','field':('creation_ts',None),'event':(reporter,creation_ts,'OPENED',None)})
        if full_report:
            bug_events.append({'type':'delta_ts','field':('delta_ts',None),'event':(assigned_to,delta_ts,'MODIFIED',None)})
        bug_events.sort(cmp=lambda x,y: cmp(x['event'][1],y['event'][1]),reverse=False)

        if full_report:
            if not (bug_events[-1]['event'][2] in ('CLOSED','FIXED','RESOLVED','MOVED','INVALID','WONTFIX','DUPLICATE')):
                bug_events.append({'type':'now','field':('NULL',None),'event':(assigned_to,now,'NOW',None)})

        last_timestamp=0
        for event in bug_events:
            if last_timestamp == 0:
                last_timestamp=event['event'][1]
                event['delay']=0
                continue
            event['delay']=event['event'][1]-last_timestamp
            last_timestamp=event['event'][1]
        event_list[bug]=bug_events

    return event_list

def getTimelines(bdb,bug_list):
    users={}
    for (bug,bug_desc,creation_ts,delta_ts) in bug_list:
        c=bdb.cursor()
        c.execute('select who,unix_timestamp(bug_when),added from bugs_activity where bug_id=%s order by bug_when',(bug))
        last_timestamp=creation_ts
        while(True):
            row=c.fetchone()
            if row == None:
                break
            (who,bug_when,added)=row
            if last_timestamp==0:
                last_timestamp=bug_when
                continue
            if not users.has_key(who):
                users[who]=[]
            # users[who].append((bug,str(datetime.timedelta(seconds=bug_when-last_timestamp))))
            users[who].append((bug,bug_when-last_timestamp,added,bug_desc))
            last_timestamp=bug_when
            
    return users

def getAssignmentResponseTimes(bdb,bug_list,pi):
    users={}
    for (bug,bug_desc,creation_ts,delta_ts) in bug_list:
        c=bdb.cursor()
        # c.execute('select ba.who,unix_timestamp(ba.bug_when),ba.added,p.userid from bugs_activity as ba, profiles as p where ba.bug_id=%s and p.login_name=ba.added order by ba.bug_when',(bug))
        c.execute("""select ba.who,unix_timestamp(ba.bug_when),ba.added,p1.userid,ba.removed,p2.userid 
                        from bugs_activity as ba 
                          left join profiles as p1 on p1.login_name=ba.added 
                          left join profiles as p2 on p2.login_name=ba.removed
                        where ba.bug_id=%s order by ba.bug_when""",(bug))
        last_timestamp=creation_ts
        while(True):
            row=c.fetchone()
            if row == None:
                break
            (who,bug_when,added,added_userid,removed,removed_userid)=row
            if not users.has_key(who):
                users[who]=[]
            if added_userid == pi.userid:
                ## reset counter
                last_timestamp=bug_when
                pass
            if removed_userid == pi.userid:
                ## starting counter
                users[who].append((bug,bug_when-last_timestamp,added,bug_desc))
                # last_timestamp=bug_when
                pass
            # users[who].append((bug,str(datetime.timedelta(seconds=bug_when-last_timestamp))))
            # users[who].append((bug,bug_when-last_timestamp,added,bug_desc))
            ## if added_userid==who:
                ## last_timestamp=bug_when
            
    return users

def printEvents(el,bl,pi):
    bug_mapping={}
    for b in bl:
        bug_mapping[b[0]]=b

    sorted_bugs=el.keys()
    sorted_bugs.sort()
    avg_delays=[]
    median_delays=[]
    for bug in sorted_bugs:
        print "=====> ",bug,bug_mapping[bug]
        last_assigned=None
        cumulative_delay=0
        delays=[]
        for be in el[bug]:
            relevant=False
            cumulative_delay=cumulative_delay+be['delay']
            if be['event'][2] == pi.login_name:
                # bug was assigned to the person
                # start counting
                cumulative_delay=0
                if last_assigned!=pi.login_name:
                    cumulative_delay=0
                relevant=True
            if be['event'][3] == pi.login_name:
                # bug got reassigned to someone else
                # print "DEBUG: adding delay ",cumulative_delay
                # print "DEBUG: Delay: ",cumulative_delay
                delays.append(cumulative_delay)
                cumulative_delay=0
                relevant=True

            ### This one added too much...
            if be['type'] == 'now':
                # last entry
                print last_assigned,cumulative_delay
                delays.append(cumulative_delay)

            if be['field'][0] == 'assigned_to':
                last_assigned=be['event'][2]
            if relevant:
                ## print be
                pass
            # print be
        if delays:
            avg_delay=sum(delays)/len(delays)
            mean_delay=numpy.mean(delays)
            median_delay=numpy.median(delays)
            # avg_delay=datetime.timedelta(seconds=sum(delays)/len(delays))
            print "   Bug Average delay: %s" % (str(datetime.timedelta(seconds=numpy.average(delays))))
            print "   Bug Mean delay: %s" % (str(datetime.timedelta(seconds=numpy.mean(delays))))
            print "   Bug Median delay: %s" % (str(datetime.timedelta(seconds=numpy.median(delays))))
            print "   Bug Std delay: %s" % (str(datetime.timedelta(seconds=numpy.std(delays))))
            # print "Bug Var delay: %s" % (str(datetime.timedelta(seconds=numpy.var(delays))))
        else:
            avg_delay=be['delay']
            print "   -Bug Average delay: %s" % (str(datetime.timedelta(seconds=avg_delay)))

        avg_delays.append(avg_delay)

    overall_avg= sum(avg_delays)/len(avg_delays)
    print "=== TOTALS ==="
    print "Overall avg delay: ",str(datetime.timedelta(seconds=overall_avg))
    print "Overall median delay: ",str(datetime.timedelta(seconds=numpy.median(avg_delays)))



def printTimelines(timelines,pi):
    prev_bug=''
    response_times=[]
    for entry in timelines[pi.userid]:
        if entry[0] != prev_bug:
            print "Bug %s : %s" % (entry[0],entry[3])
        print "      %s : %s" % (str(datetime.timedelta(seconds=entry[1])),entry[2])
        response_times.append(entry[1])
        prev_bug=entry[0]

    print "Average: %s" % (str(datetime.timedelta(seconds=sum(response_times)/len(response_times))))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Bugzilla activity report')
    parser.add_argument('login_name',type=str,help="Login Name",
                        metavar='<login_name>', default=None)
    parser.add_argument('--config',type=str,help="Config file",
                        required=False,default='bugzillarc')
    
    parser.add_argument('--algorithm',type=str,help="Algorithm to use",
                        required=False,choices=('chat','assignment','events'),default='events')
    
    parser.add_argument('--full',help="Full report: consider even open cases",action='store_const',
                        const=True, default=False, required=False)
    

    args=parser.parse_args(sys.argv[1:])
    login_name=args.login_name
    config_file=args.config
    bdb_info=loadDBInfo(config_file)

    bdb=MySQLdb.connect(**bdb_info)
    pi=getPersonInfo(bdb,login_name)
    print "Report for : ",pi.realname
    bug_id_list=getBugList(bdb,pi)

    ## for bid in bug_id_list:
        ## print bid

    if args.algorithm == 'chat':
        timelines=getTimelines(bdb,bug_id_list)
        printTimelines(timelines,pi)
    elif args.algorithm == 'assignment':
        timelines=getAssignmentResponseTimes(bdb,bug_id_list,pi)
        printTimelines(timelines,pi)
    elif args.algorithm == 'events':
        el=getEventList(bdb,bug_id_list,args.full)
        printEvents(el,bug_id_list,pi)

