"""
github_buildbot.py is based on git_buildbot.py

github_buildbot.py will determine the repository information from the JSON
HTTP POST it receives from github.com and build the appropriate repository.
If your github repository is private, you must add a ssh key to the github
repository for the user who initiated the build on the buildslave.

"""

import logging
import os
import re
import sys
import tempfile
import traceback

from optparse import OptionParser
from twisted.cred import credentials
from twisted.internet import reactor
from twisted.spread import pb
from twisted.web import resource
from twisted.web import server

try:
    import json
except ImportError:
    import simplejson as json

root = logging.getLogger()

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)
root.setLevel(logging.DEBUG)




def main():
    """
    The main event loop that starts the server and configures it.
    """
    usage = "usage: %prog [options]"
    parser = OptionParser(usage)

    parser.add_option("-p", "--port",
                      help="Port the HTTP server listens to for the GitHub Service Hook"
                      + " [default: %default]", default=4000, type=int, dest="port")

    parser.add_option("-m", "--buildmaster",
                      help="Buildbot Master host and port. ie: localhost:9989 [default:"
                      + " %default]", default="localhost:9989", dest="buildmaster")

    parser.add_option("-l", "--log",
                      help="The absolute path, including filename, to save the log to"
                      + " [default: %default]",
                      default=tempfile.gettempdir() + "/github_buildbot.log",
                      dest="log")

    parser.add_option("-L", "--level",
                      help="The logging level: debug, info, warn, error, fatal [default:"
                      + " %default]", default='warn', dest="level")

    parser.add_option("-g", "--github",
                      help="The github server.  Changing this is useful if you've specified"
                      + "  a specific HOST handle in ~/.ssh/config for github "
                      + "[default: %default]", default='github.com',
                      dest="github")

    parser.add_option("--pidfile",
                      help="Write the process identifier (PID) to this file on start."
                      + " The file is removed on clean exit. [default: %default]",
                      default=None,
                      dest="pidfile")

    (options, _) = parser.parse_args()

    if options.pidfile:
        with open(options.pidfile, 'w') as f:
            f.write(str(os.getpid()))

    levels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'error': logging.ERROR,
        'fatal': logging.FATAL,
    }

    filename = options.log
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(filename=filename, format=log_format,
                        level=levels[options.level])

    github_bot = GitHubBuildBot()
    github_bot.github = options.github
    github_bot.master = options.buildmaster

    site = server.Site(github_bot)
    reactor.listenTCP(options.port, site)
    root.debug('running reactor')
    reactor.run()

    if options.pidfile and os.path.exists(options.pidfile):
        os.unlink(options.pidfile)

root.debug('starting...')
main()
