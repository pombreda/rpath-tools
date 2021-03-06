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

import os
import pywbem

import testbaserepo

import concrete_job
import installation_service

class Test(testbaserepo.TestCase):
    def testSoftwareInstallationService(self):
        prov, objP  = self.getProviderSoftwareInstallationService()
        # This is data coming from testbaserepo's CimomHandle
        self.failUnlessEqual(
            [ x.keybindings for x in prov.MI_enumInstanceNames(self.env, objP) ],
            [ {'CreationClassName': 'VAMI_SoftwareInstallationService',
               'Name': 'rPath Software Installation Service',
               'SystemName': 'localhost.localdomain',
               'SystemCreationClassName': 'Linux_ComputerSystem'} ])

        props = [ x.properties.copy() for x in prov.MI_enumInstances(self.env,
                  objP, []) ]
        self.failUnlessEqual(len(props), 1)

        props = sorted([ (x, y.value) for (x, y) in props[0].items() ])
        self.failUnlessEqual(props, [
            ('AutomaticUpdates', 0L),
            ('CreationClassName', 'VAMI_SoftwareInstallationService'),
            ('Name', 'rPath Software Installation Service'),
            ('RepositoryAddress', 'foobar'),
            ('SystemCreationClassName', 'Linux_ComputerSystem'),
            ('SystemName', 'localhost.localdomain')
        ])

        inst = prov.MI_getInstance(self.env, objP, [])

        error = self.failUnlessRaises(pywbem.CIMError,
            prov.MI_createInstance, self.env, objP)
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            prov.MI_modifyInstance, self.env, inst, [])
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            prov.MI_deleteInstance, self.env, objP)
        self.failUnlessEqual(error.args, (7, ))

        unsupportedMethods = [
            ("ChangeAffectedElementsAssignedSequence",
                dict(ManagedElements = [], AssignedSequence = [])),
            ("CheckSoftwareIdentity", {}),
            ("InstallFromByteStream", {}),
            ("InstallFromURI", {}),
            ("RequestStateChange", {}),
            ("SetAutomaticUpdates", {}),
            ("SetProxyServerAddress", {}),
            ("SetRepositoryAddress", {}),
            ("StartService", {}),
            ("StopService", {}),
        ]
        for method, params in unsupportedMethods:
            error = self.failUnlessRaises(pywbem.CIMError,
                prov.MI_invokeMethod, self.env, objP, method, params)
            self.failUnlessEqual(error.args, (16, ))

    def _listRepos(self, repos, troveName):
        trvSpec = (troveName, None, None)
        trvMap = repos.findTroves(self.defLabel, [trvSpec],
            requireLatest = False, getLeaves = False)
        trvList = trvMap.values()[0]
        trvList.sort()
        return trvList

    def testCheckAvailableUpdates(self):
        repos = self.openRepository()
        for v in ["1", "2"]:
            self.addComponent("foo:runtime", v)
            self.addCollection("foo", v, [":runtime"])
            trv = self.addCollection("group-bar", v, [ "foo" ])

        self.updatePkg(["group-bar=1"])
        # Now we need to find the timestamps
        trvList = self._listRepos(repos, 'group-bar')
        installedTrvVersion = trvList[0][1].freeze()
        availableTrvVersion = trvList[1][1].freeze()

        prov, objP  = self.getProviderSoftwareInstallationService()
        # Invoke method
        ret, params = prov.MI_invokeMethod(self.env, objP, "CheckAvailableUpdates", {})
        self.failUnlessEqual(ret[1], 4096)

        jobObjectPath = params['job'][1]
        self.failUnless(jobObjectPath.keybindings['InstanceID'].startswith("com.rpath:"))

        jobState, jobInst, jProv = self.waitJob(jobObjectPath, timeout = 2)
        self.failUnlessEqual(jobState, jProv.Values.JobState.Completed)

        esiProv, esiObjPath = self.getProviderElementSoftwareIdentity()
        esis = ( x for x in esiProv.MI_enumInstances(self.env, esiObjPath, []) )
        instanceIds = dict(
            (x.properties['Antecedent'].value.keybindings['InstanceID'], None)
            for x in esis)
        installedInstanceId = 'rpath.com:group-bar=%s[]' % installedTrvVersion
        self.assertIn(installedInstanceId, instanceIds)
        instanceIds.pop(installedInstanceId)
        self.failUnlessEqual(len(instanceIds), 1)
        availInstanceId = instanceIds.keys()[0]
        self.failUnless(availInstanceId.startswith("rpath.com:"))
        return availInstanceId

    def testCheckAvailableUpdatesNoUpdates(self):
        repos = self.openRepository()
        for v in ["1", ]:
            self.addComponent("foo:runtime", v)
            self.addCollection("foo", v, [":runtime"])
            self.addCollection("group-bar", v, [ "foo" ])

        self.updatePkg(["group-bar=1"])

        prov, objP  = self.getProviderSoftwareInstallationService()
        # Invoke method
        ret, params = prov.MI_invokeMethod(self.env, objP,
            "CheckAvailableUpdates", {})
        self.failUnlessEqual(ret[1], 4096)

        jobObjectPath = params['job'][1]
        self.failUnless(jobObjectPath.keybindings['InstanceID'].startswith("com.rpath:"))

        jobState, jobInst, jProv = self.waitJob(jobObjectPath, timeout = 2)
        self.failUnlessEqual(jobState, jProv.Values.JobState.Completed)

    def testInstallFromSoftwareIdentity(self):
        # Run the other test first
        availInstanceId = self.testCheckAvailableUpdates()

        _, siObjPath = self.getProviderSoftwareIdentity()
        siObjPath['InstanceID'] = availInstanceId

        sisProv, sisObjPath = self.getProviderSoftwareInstallationService()

        ret, params = sisProv.MI_invokeMethod(self.env, sisObjPath,
            "InstallFromSoftwareIdentity", dict(Source = siObjPath))

        self.failUnlessEqual(ret[1], 4096)

        jobObjectPath = params['job'][1]

        jobState, jobInst, jProv = self.waitJob(jobObjectPath, timeout = 10)
        self.failUnlessEqual(jobState, jProv.Values.JobState.Completed)

        nvfs = [ x for x in self.getConaryClient().db.iterAllTroves() ]
        self.failUnlessEqual(
            sorted([ (x[0], str(x[1]), str(x[2])) for x in nvfs ]),
            [('foo', '/localhost@rpl:linux/2-1-1', ''),
             ('foo:runtime', '/localhost@rpl:linux/2-1-1', ''),
             ('group-bar', '/localhost@rpl:linux/2-1-1', '')])

    def _setupRepo(self):
        for v in ["1", "2"]:
            self.addComponent("foo:runtime", v)
            self.addCollection("foo", v, [":runtime"])
            trv = self.addCollection("group-foo", v, [ "foo" ])
            self.addComponent("bar:runtime", v)
            self.addCollection("bar", v, [":runtime"])
            trv = self.addCollection("group-bar", v, [ "bar" ])

        self.updatePkg(["group-foo=1", "group-bar=1"])

    def testInstallFromNetworkLocations(self):
        import RPATH_SoftwareInstallationService
        RPATH_SoftwareInstallationService.pythonPath = "/usr/bin/python"

        defLabel = self.defLabel
        mode = "migrate"

        class Popen:
            def __init__(self, *args, **kwargs):
                import concrete_job
                import installation_service
                callArgs = args[0]
                concreteJob = concrete_job.UpdateJob().new()
                _flags = {}
                _flags[mode] = True
                flags = installation_service.UpdateFlags(**_flags)
                concreteJob.startUpdateOperation(
                    [sources % defLabel],
                    flags)
                self.jobId = concreteJob.get_job_id()

            def wait(self):
                return None

            def communicate(self):
                return self.jobId, None

        self.mock(RPATH_SoftwareInstallationService.subprocess, "Popen", Popen)

        self._setupRepo()
        _, siObjPath = self.getProviderSoftwareIdentity()

        sisProv, sisObjPath = self.getProviderSoftwareInstallationService()

        # Update
        InstallOptions = [sisProv.Values.InstallFromNetworkLocations.InstallOptions.Update]
        InstallOptionValues = [None]
        sources = "group-foo=/%s/2-1-1"
        mode = "update"
        ret, params = sisProv.MI_invokeMethod(self.env, sisObjPath,
            "InstallFromNetworkLocations",
            dict(
                ManagementNodeAddresses = ['1.1.1.1', '2.2.2.2'],
                Sources = ["group-foo=/%s/2-1-1" % self.defLabel],
                InstallOptions = InstallOptions,
                InstallOptionValues = InstallOptionValues))

        self.failUnlessEqual(ret[1], 4096)

        jobObjectPath = params['job'][1]

        jobState, jobInst, jProv = self.waitJob(jobObjectPath, timeout = 10)
        self.failUnlessEqual(jobState, jProv.Values.JobState.Completed)

        rlProv, rlObjectPath = self.getProviderRecordLog()
        rlObjectPath['InstanceId'] = jobObjectPath['InstanceId']
        recordLogInst = rlProv.MI_getInstance(self.env, rlObjectPath, None)
        # Make sure we got some logs here
        self.failUnlessEqual(
            recordLogInst.properties['CurrentNumberOfRecords'].value,
            31)

        rleProv, rleObjectPath = self.getProviderLogEntry()
        logEntryContents = []
        for leInst in rleProv.MI_enumInstances(self.env, rleObjectPath, []):
            logEntryContents.append(leInst.properties['RecordData'].value)
        logId = leInst.properties['LogInstanceID'].value
        self.failUnlessEqual(len(logEntryContents), 31)
        self.failUnlessEqual(logEntryContents[-1], "Done")

        ruolProv, ruolObjectPath = self.getProviderUseOfLog()
        ret = []
        for uol in ruolProv.MI_enumInstances(self.env, ruolObjectPath, []):
            left = uol.properties['Antecedent'].value
            right = uol.properties['Dependent'].value
            ret.append((left.classname, left.keybindings['InstanceID'],
                right.classname, right.keybindings['InstanceID']))
        self.failUnlessEqual(len(ret), 1)
        self.failUnlessEqual(ret[0][0], 'RPATH_RecordLog')
        self.failUnlessEqual(ret[0][2], 'RPATH_UpdateConcreteJob')
        self.failUnlessEqual(ret[0][1].replace('recordLogs', 'jobs'),
            ret[0][3])
        self.failUnlessEqual(ret[0][1], logId)

        nvfs = [ x for x in self.getConaryClient().db.iterAllTroves() ]
        self.failUnlessEqual(
            sorted([ (x[0], str(x[1]), str(x[2])) for x in nvfs ]),
            [('bar', '/localhost@rpl:linux/1-1-1', ''),
             ('bar:runtime', '/localhost@rpl:linux/1-1-1', ''),
             ('foo', '/localhost@rpl:linux/2-1-1', ''),
             ('foo:runtime', '/localhost@rpl:linux/2-1-1', ''),
             ('group-bar', '/localhost@rpl:linux/1-1-1', ''),
             ('group-foo', '/localhost@rpl:linux/2-1-1', '')])

        # Migrate group-bar
        InstallOptions = [sisProv.Values.InstallFromNetworkLocations.InstallOptions.Migrate]
        InstallOptionValues = [None]
        sources = "group-bar=/%s/2-1-1"
        mode = "migrate"
        ret, params = sisProv.MI_invokeMethod(self.env, sisObjPath,
            "InstallFromNetworkLocations",
            dict(
                ManagementNodeAddresses = ['1.1.1.1', '2.2.2.2'],
                Sources = ["group-bar=/%s/2-1-1" % self.defLabel],
                InstallOptions = InstallOptions,
                InstallOptionValues = InstallOptionValues))

        self.failUnlessEqual(ret[1], 4096)

        jobObjectPath = params['job'][1]

        jobState, jobInst, jProv = self.waitJob(jobObjectPath, timeout = 10)
        self.failUnlessEqual(jobState, jProv.Values.JobState.Completed)

        nvfs = [ x for x in self.getConaryClient().db.iterAllTroves() ]
        self.failUnlessEqual(
            sorted([ (x[0], str(x[1]), str(x[2])) for x in nvfs ]),
            [('bar', '/localhost@rpl:linux/2-1-1', ''),
             ('bar:runtime', '/localhost@rpl:linux/2-1-1', ''),
             ('group-bar', '/localhost@rpl:linux/2-1-1', ''),
            ])

        # Test GetError too, while we're at it
        ret, params = jProv.MI_invokeMethod(self.env, jobObjectPath,
            'GetError', {})
        self.failUnlessEqual(params, {})
        self.failUnlessEqual(ret, ('uint32', 0L))
        import concrete_job
        jobId = jobObjectPath['InstanceID'].split(':', 1)[-1]
        jobId = jobId.split('/', 1)[-1]
        job = concrete_job.AnyJob.load(jobId)
        job.concreteJob.state = 'Exception'

        ret, params = jProv.MI_invokeMethod(self.env, jobObjectPath,
            'GetError', {})
        self.failUnlessEqual(ret, ('uint32', 2L))
        self.failUnlessEqual(params, {})

        job.concreteJob.content = 'Blahblah'
        ret, params = jProv.MI_invokeMethod(self.env, jobObjectPath,
            'GetError', {})
        self.failUnlessEqual(ret, ('uint32', 0L))
        self.failUnlessEqual(params['Error'][1].properties['Message'].value,
            'Blahblah')

    def testEnumerateElementSoftwareIdentity(self):
        repos = self.openRepository()
        for v in ["1", ]:
            self.addComponent("foo:runtime", v)
            self.addCollection("foo", v, [":runtime"])
            self.addCollection("group-bar", v, [ "foo" ])

        self.updatePkg(["group-bar=1"])
        # Now we need to find the timestamps
        trvList = self._listRepos(repos, 'group-bar')
        installedTrvVersion = trvList[0][1].freeze()

        modelPath = installation_service.util.joinPaths(self.cfg.root, self.cfg.modelPath)
        installation_service.util.mkdirChain(os.path.dirname(modelPath))
        file(modelPath, "w").write("Nothing to see here\n")

        esiProv, esiObjPath = self.getProviderElementSoftwareIdentity()
        esis = [ x.properties.copy()
            for x in esiProv.MI_enumInstances(self.env, esiObjPath, []) ]
        self.failUnlessEqual(len(esis), 2)
        esi = [ x for x in esis if x['Antecedent'].value['InstanceID'] != 'com.rpath.conary:system_model' ][0]
        self.failUnlessEqual(sorted(esi.keys()),
            ['Antecedent', 'Dependent', 'ElementSoftwareStatus',
             'UpgradeCondition'])
        self.failUnlessEqual(esi['ElementSoftwareStatus'].value, [2, 6])
        self.failUnlessEqual(esi['UpgradeCondition'].value, 3)

        antecedent = esi['Antecedent']
        dependent = esi['Dependent']
        self.failUnlessEqual(antecedent.type, "reference")
        self.failUnlessEqual(dependent.type, "reference")

        antecedent = antecedent.value
        dependent = dependent.value
        self.failUnlessEqual(antecedent.items(),
            [('InstanceID', 'rpath.com:group-bar=%s[]' % installedTrvVersion)])

        esi = [ x for x in esis if x['Antecedent'].value['InstanceID'] == 'com.rpath.conary:system_model' ][0]
        self.failUnlessEqual(sorted(esi.keys()),
            ['Antecedent', 'Dependent', 'ElementSoftwareStatus',
             'UpgradeCondition'])
        self.failUnlessEqual(esi['ElementSoftwareStatus'].value, [9])

        self.failUnlessEqual(dependent.items(),
            [('CreationClassName', 'Linux_ComputerSystem'),
             ('Name', 'localhost.localdomain')])

        # Same thing, but enumerate instance names
        esis = [ x.keybindings.copy()
            for x in esiProv.MI_enumInstanceNames(self.env, esiObjPath) ]
        self.failUnlessEqual(len(esis), 2)
        esi = [ x for x in esis if x['Antecedent']['InstanceID'] != 'com.rpath.conary:system_model' ][0]
        self.failUnlessEqual(sorted(esi.keys()),
            ['Antecedent', 'Dependent'])

        groupObjectPath = [ x
            for x in esiProv.MI_enumInstanceNames(self.env, esiObjPath)
            if x['Antecedent']['InstanceID'] != 'com.rpath.conary:system_model'
            ][0]
        systemModelObjectPath = [ x
            for x in esiProv.MI_enumInstanceNames(self.env, esiObjPath)
            if x['Antecedent']['InstanceID'] == 'com.rpath.conary:system_model'
            ][0]

        inst = esiProv.MI_getInstance(self.env, groupObjectPath,
            ['ElementSoftwareStatus', 'UpgradeCondition'])
        self.failUnlessEqual(sorted(inst.keys()),
            ['Antecedent', 'Dependent', 'ElementSoftwareStatus',
             'UpgradeCondition'])

        inst = esiProv.MI_getInstance(self.env, systemModelObjectPath,
            ['ElementSoftwareStatus', 'UpgradeCondition'])
        self.failUnlessEqual(sorted(inst.keys()),
            ['Antecedent', 'Dependent', 'ElementSoftwareStatus',
             'UpgradeCondition'])

        inst = list(esiProv.MI_enumInstances(self.env, groupObjectPath, []))[0]
        self.failUnlessEqual(sorted(inst.keys()),
            ['Antecedent', 'Dependent', 'ElementSoftwareStatus',
             'UpgradeCondition'])

        error = self.failUnlessRaises(pywbem.CIMError,
            esiProv.MI_createInstance, self.env, esiObjPath)
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            esiProv.MI_modifyInstance, self.env, inst, [])
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            esiProv.MI_deleteInstance, self.env, esiObjPath)
        self.failUnlessEqual(error.args, (7, ))


    def testEnumerateSoftwareIdentity(self):
        repos = self.openRepository()
        for v in ["1", ]:
            self.addComponent("foo:runtime", v)
            self.addCollection("foo", v, [":runtime"])
            self.addCollection("group-bar", v, [ "foo" ])

        self.updatePkg(["group-bar=1"])
        # Now we need to find the timestamps
        trvList = self._listRepos(repos, 'group-bar')
        installedTrvVersion = trvList[0][1].freeze()

        modelPath = installation_service.util.joinPaths(self.cfg.root, self.cfg.modelPath)
        installation_service.util.mkdirChain(os.path.dirname(modelPath))
        file(modelPath, "w").write("Nothing to see here\n")

        siProv, siObjPath = self.getProviderSoftwareIdentity()
        sis = [ x.properties.copy()
            for x in siProv.MI_enumInstances(self.env, siObjPath, []) ]
        self.failUnlessEqual(len(sis), 2)
        si = [ x for x in sis
            if x['InstanceID'].value != 'com.rpath.conary:system_model' ][0]

        # Grab the version of the installed group-bar
        cli = self.getConaryClient()
        trvList = cli.getPrimaryLocalUpdates()
        self.failUnlessEqual(len(trvList), 1)
        trvSpec = trvList[0]
        versionTimestamp = int(trvSpec[2][0].trailingRevision().getTimestamp())
        groupVersionTimestamp = versionTimestamp

        d = dict((x, y.value) for (x, y) in si.items())
        revisionNumber = d.pop('RevisionNumber')
        buildNumber = d.pop('BuildNumber')
        largeBuildNumber = d.pop('LargeBuildNumber')
        releaseDate = d.pop('ReleaseDate')

        self.failUnlessEqual(largeBuildNumber, versionTimestamp)
        self.failUnlessEqual(revisionNumber,
            (versionTimestamp & 0xFFFF0000) >> 16)
        self.failUnlessEqual(buildNumber, versionTimestamp & 0xFFFF)

        self.failUnlessEqual(sorted(d.items()), [
            ('Description', 'group-bar'),
            ('ElementName', 'group-bar'),
            ('HealthState', 5L),
            ('IdentityInfoType', ['VMware-VAMI:VendorUUID', 'VMware-VAMI:ProductRID', 'VMware-VAMI:VendorURL', 'VMware-VAMI:ProductURL', 'VMware-VAMI:SupportURL', 'VMware-VAMI:UpdateInfo']),
            ('IdentityInfoValue', ['com.rpath', 'localhost@rpl:linux', 'http://www.rpath.org/rbuilder', 'http://www.rpath.org/project/remote-update', 'http://www.rpath.org/rbuilder', '']),
            ('InstanceID', 'rpath.com:group-bar=%s[]' % installedTrvVersion),
            ('IsEntity', True),
            ('IsLargeBuildNumber', True),
            ('MajorVersion', 0L),
            ('Manufacturer', 'rPath, Inc.'),
            ('MinorVersion', 0L),
            ('Name', 'group-bar'),
            ('OperatingStatus', 16L),
            ('PrimaryStatus', 1L),
            ('TargetOSTypes', [36L]),
            ('VersionString', '%s[]' % installedTrvVersion)
        ])

        si = [ x for x in sis
            if x['InstanceID'].value == 'com.rpath.conary:system_model' ][0]

        versionTimestamp = int(os.stat(modelPath).st_mtime)
        systemModelVersionTimestamp = versionTimestamp

        d = dict((x, y.value) for (x, y) in si.items())
        revisionNumber = d.pop('RevisionNumber')
        buildNumber = d.pop('BuildNumber')
        largeBuildNumber = d.pop('LargeBuildNumber')
        releaseDate = d.pop('ReleaseDate')

        self.failUnlessEqual(largeBuildNumber, versionTimestamp)
        self.failUnlessEqual(revisionNumber,
            (versionTimestamp & 0xFFFF0000) >> 16)
        self.failUnlessEqual(buildNumber, versionTimestamp & 0xFFFF)

        self.failUnlessEqual(sorted(d.items()), [
            ('Description', 'system model'),
            ('ElementName', 'system model'),
            ('HealthState', 5L),
            ('IdentityInfoType', ['VMware-VAMI:VendorUUID', 'VMware-VAMI:ProductRID', 'VMware-VAMI:VendorURL', 'VMware-VAMI:ProductURL', 'VMware-VAMI:SupportURL', 'VMware-VAMI:UpdateInfo']),
            ('IdentityInfoValue', ['com.rpath', 'system model', 'http://www.rpath.org/rbuilder', 'http://www.rpath.org/project/remote-update', 'http://www.rpath.org/rbuilder', '']),
            ('InstanceID', 'com.rpath.conary:system_model'),
            ('IsEntity', True),
            ('IsLargeBuildNumber', True),
            ('MajorVersion', 0L),
            ('Manufacturer', 'rPath, Inc.'),
            ('MinorVersion', 0L),
            ('Name', 'system model'),
            ('OperatingStatus', 16L),
            ('PrimaryStatus', 1L),
            ('TargetOSTypes', [36L]),
            ('VersionString', '%s' % file(modelPath).read()),
        ])


        # Same thing, but enumerate instance names
        sis = [ x.keybindings.copy()
            for x in siProv.MI_enumInstanceNames(self.env, siObjPath) ]
        self.failUnlessEqual(len(sis), 2)
        si = [ x for x in sis
            if x['InstanceID'] != 'com.rpath.conary:system_model' ][0]
        self.failUnlessEqual(sorted(si.items()), [
            ('InstanceID', 'rpath.com:group-bar=%s[]' % installedTrvVersion)
        ])
        si = [ x for x in sis
            if x['InstanceID'] == 'com.rpath.conary:system_model' ][0]
        self.failUnlessEqual(sorted(si.items()), [
            ('InstanceID', 'com.rpath.conary:system_model'),
        ])

        siObjPath.keybindings['InstanceID'] = 'rpath.com:group-bar=%s[]' % installedTrvVersion
        inst = siProv.MI_getInstance(self.env, siObjPath, [])
        self.failUnlessEqual(sorted(inst.items()), [
            ('InstanceID', 'rpath.com:group-bar=%s[]' % installedTrvVersion)
        ])

        siObjPath.keybindings['InstanceID'] = 'com.rpath.conary:system_model'
        inst = siProv.MI_getInstance(self.env, siObjPath, [])
        self.failUnlessEqual(sorted(inst.items()), [
            ('InstanceID', 'com.rpath.conary:system_model'),
        ])

        insts = sorted((x['InstanceID'], x['ElementName'])
            for x in siProv.MI_enumInstances(self.env, siObjPath, []))
        self.assertEquals(insts,
            [
                ('com.rpath.conary:system_model', 'system model'),
                ('rpath.com:group-bar=%s[]' % installedTrvVersion, 'group-bar'),
            ])

        error = self.failUnlessRaises(pywbem.CIMError,
            siProv.MI_createInstance, self.env, siObjPath)
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            siProv.MI_modifyInstance, self.env, inst, [])
        self.failUnlessEqual(error.args, (7, ))
        error = self.failUnlessRaises(pywbem.CIMError,
            siProv.MI_deleteInstance, self.env, siObjPath)
        self.failUnlessEqual(error.args, (7, ))
