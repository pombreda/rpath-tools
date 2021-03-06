#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import logging
import os
import os.path
import pwd
import sys
import time

from conary.lib import util

from rpath_tools.client import config

from lxml import etree
from rpath_tools.client.sysdisco import scanner

from rpath_tools.client.register import LocalUuid

logger = logging.getLogger('client')

def main(cfg=None):
    if not cfg:
        cfg = config.RpathToolsConfiguration()
        cfg.topDir = '/etc/conary'
    r = Scanner(cfg)
    r.scanSystem()
    return r.surveyScanner.uuid, r.surveyPath


class Scanner(object):

    def __init__(self, cfg, deviceName=None):
        self.cfg = cfg
        self.surveyScanner = scanner.SurveyScanner()
        self.localUuidObj = LocalUuid(self.cfg.localUuidFilePath,
                                 self.cfg.localUuidOldDirectoryPath,
                                 deviceName)
        self.targetSystemId = self.localUuidObj.targetSystemId
        self.surveyPath = None
        self.survey = None
        self.surveyUuid = None

    def setDeviceName(self, deviceName):
        self.localUuidObj.deviceName = deviceName
        self.localUuid = self.localUuidObj.uuid

    @classmethod
    def scanner(self, cfg=None):
        if not cfg:
            cfg = config.RpathToolsConfiguration()
        return Scanner(cfg)


    def writeSurveytoStore(self, xml, store, uuid=None,  uid=None, gid=None):
        """
        Write the Survey to the store, using the supplied uid and gid
        """
        if not uuid:
            uuid = self.surveyScanner.uuid
        self.surveyPath = os.path.join(store, 'survey-%s.xml' % uuid )
        if self.surveyPath is None:
            # Already written
            return None
        logger.info("Writing survey as %s" % self.surveyPath)
        util.mkdirChain(os.path.dirname(self.surveyPath))
        f = util.AtomicFile(self.surveyPath, chmod=0600)
        f.write(xml)
        f.commit()
        if uid or gid:
            os.chown(self.surveyPath, uid, gid)
        return self.surveyPath


    def removeSurveyFromStore(self, uuid, store):
        self.surveyPath = os.path.join(store, 'survey-%s.xml' % uuid)
        if self.surveyPath is None:
            return False
        util.removeIfExists(self.surveyPath)
        return True


    @property
    def sfcbConfig(self):
        if self._sfcbCfg is None:
            self._sfcbCfg = self.parseSfcbCfg()
        return self._sfcbCfg


    def parseSfcbCfg(self):
        sfcbFilePath = self.cfg.sfcbConfigurationFile
        try:
            f = file(sfcbFilePath)
        except IOError:
            return {}
        # Get rid of all comments and empty lines
        lines = (x.strip() for x in f)
        lines = (x for x in lines if x and not x.startswith('#'))
        cfgVals = (x.split(':', 1) for x in lines)
        cfgVals = (x for x in cfgVals if len(x) == 2)
        return dict((x.strip(), y.strip()) for (x, y) in cfgVals)


    @classmethod
    def _getUserIds(cls, user):
        try:
            strct = pwd.getpwnam(user)
            return strct.pw_uid, strct.pw_gid
        except KeyError:
            return (0, 0)


    def scanSystem(self):
        logger.info('Attempting to run survey on %s' % self.localUuidObj.uuid)
        start = time.time()
        start_proc = time.clock()
        surveyed = self._scanner([])
        if surveyed:
            proctime = time.clock() - start_proc
            scantime = time.time() - start
            logger.info('    Survey succeeded\n'
                        '        Survey File   : %s\n'
                        '        Scan Time     : %s\n'
                        '        Process Time  : %s\n' %
                            (surveyed, scantime,proctime)
                        )
            return True
        return False

    def scanSystemCIM(self, desiredTopLevelItems):
        '''use this from CIM as it removes prints'''
        logger.info('Attempting to run survey on %s' % self.localUuidObj.uuid)
        start = time.time()
        start_proc = time.clock()
        surveyed = self._scanner(desiredTopLevelItems)
        if surveyed:
            proctime = time.clock() - start_proc
            scantime = time.time() - start
            logger.info('    Survey succeeded\n'
                        '        Survey File   : %s\n'
                        '        Scan Time     : %s\n'
                        '        Process Time  : %s\n' %
                            (surveyed, scantime,proctime)
                        )
            return True
        logger.error('  Survey failed.  Check the log file at %s' %
            self.cfg.logFile)
        return False


    def _scanner(self, desiredTopLevelItems):
        self.survey, self.surveyUuid = self._scan_system(desiredTopLevelItems)
        if self.survey is None:
            return self.survey
        # If the server returned something back, save
        survey_path = self.writeSurveytoStore(self.survey,
                        self.cfg.scannerSurveyStore, uuid=self.surveyUuid,
                        uid=None, gid=None)
        return survey_path


    def _scan_system(self, desiredTopLevelItems):
        dom = self.surveyScanner.toxml(desiredTopLevelItems)
        xml = etree.tostring(dom)
        return xml, self.surveyScanner.uuid


if __name__ == '__main__':
    sys.exit(main())
