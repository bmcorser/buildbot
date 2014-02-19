#!/usr/bin/env python
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


class GitHubBuildBot(resource.Resource):

    """
    GitHubBuildBot creates the webserver that responds to the GitHub Service
    Hook.
    """
    isLeaf = True
    master = None
    port = None

    def render_POST(self, request):
        """
        Responds only to POST events and starts the build process

        :arguments:
            request
                the http request object
        """
        try:
            payload = json.loads(request.content.read())
            user = payload['sender']['login']
            repo = payload['repository']['name']
            repo_url = payload['repository']['git_url']
            self.private = payload['repository']['private']
            project = request.args.get('project', None)
            if project:
                project = project[0]
            root.debug("Payload: " + str(payload))
            self.process_change(payload, user, repo, repo_url, project)
        except Exception:
            root.error("Encountered an exception:")
            for msg in traceback.format_exception(*sys.exc_info()):
                root.error(msg.strip())

    def process_change(self, payload, user, repo, repo_url, project):
        """
        Consumes the JSON as a python object and actually starts the build.

        :arguments:
            payload
                Python Object that represents the JSON sent by GitHub Service
                Hook.
        """
        action = payload['action']

        pr = payload['pull_request']
        branch = pr['head']['ref']
        if action in ('synchronize', 'opened'):
            change = [{'revision': pr['head']['sha'],
                       'revlink': pr['html_url'],
                       'comments': 'PR {0}'.format(action),
                       'who': pr['user']['login'],
                       'repository': repo_url,
                       }]

        host, port = self.master.split(':')
        port = int(port)

        factory = pb.PBClientFactory()
        deferred = factory.login(credentials.UsernamePassword("github",
                                                              "webhooks"))
        reactor.connectTCP(host, port, factory)
        deferred.addErrback(self.connectFailed)
        deferred.addCallback(self.connected, change)

    def connectFailed(self, error):
        """
        If connection is failed.  Logs the error.
        """
        root.error("Could not connect to master: %s"
                      % error.getErrorMessage())
        return error

    def addChange(self, dummy, remote, changei, src='git'):
        """
        Sends changes from the commit to the buildmaster.
        """
        root.debug("addChange %s, %s" % (repr(remote), repr(changei)))
        try:
            change = changei.next()
        except StopIteration:
            remote.broker.transport.loseConnection()
            return None

        root.info("New revision: %s" % change['revision'][:8])
        for key, value in change.iteritems():
            root.debug("  %s: %s" % (key, value))

        change['src'] = src
        deferred = remote.callRemote('addChange', change)
        deferred.addCallback(self.addChange, remote, changei, src)
        return deferred

    def connected(self, remote, changes):
        """
        Responds to the connected event.
        """
        return self.addChange(None, remote, changes.__iter__())


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

if __name__ == '__main__':
    root.debug('starting ...')
    main()
