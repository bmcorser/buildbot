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
                       'branch': pr['head']['ref'],
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

