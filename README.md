Using direct access to Bugzilla's MySQL DB fetch some usage stats

use pythonic config file "bugzillarc" (or other name is fine, look at CLI options) to define access information for DB.

using various algorithms see stats of person's activity in bugzilla::

    usage: person_report.py [-h] [--config CONFIG]
                            [--algorithm {chat,assignment,events}] [--full]
                            <login_name>
    
    Bugzilla activity report
    
      positional arguments:
      <login_name>          Login Name
    
    optional arguments:
      -h, --help            show this help message and exit
      --config CONFIG       Config file
      --algorithm {chat,assignment,events}
                            Algorithm to use
      --full                Full report: consider even open cases
