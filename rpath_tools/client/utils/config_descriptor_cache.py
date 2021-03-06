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


"""
Common module for gathering configuration descriptors for a set of troves.
"""

import logging
import itertools
from StringIO import StringIO

from conary import trove
from conary.trovetup import TroveTuple
from conary.local.database import Database
from conary.trove import _TROVEINFO_TAG_PROPERTIES

from smartform import descriptor_errors
from smartform.descriptor import SystemConfigurationDescriptor

log = logging.getLogger('config_descriptor_cache')

def _srt_by_name(a, b):
    """
    Sort groups first to avoid too many repository requests.
    """
    if a[0].startswith('group-'):
        if not b[0].startswith('group-'):
            return 1
        else:
            return cmp(a, b)
    elif b[0].startswith('group-'):
        return -1
    else:
        return cmp(a, b)


class ConfigDescriptorCache(object):
    """
    Class for generating configuration descriptors from a repository or local
    system database given a name, version, flavor tuple.

    @param repos: This should be a conary netclient or a reference to the local
                  database that implementes getTrove and getTroveInfo calls.
    """

    def __init__(self, repos):
        self._repos = repos
        self._desc_cache = {}
        self._trove_cache = {}
        self._properties_cache = {}
        self._bydefault = {}

    def getDescriptor(self, nvf):
        """
        Given a name, version, flavor tuple walk any children, grathering all
        config descriptors into a single config descriptor.
        """

        return self.getDescriptors([nvf, ]).get(nvf)

    def getDescriptors(self, nvfs):
        """
        Given a set of name, version, flavor tuples walk any children,
        gathering all config descriptors for each nvf tuple.
        """

        nvfs = [ TroveTuple(x) for x in nvfs ]

        # Cache getTroves call.
        uncached = [ x for x in nvfs if x not in self._trove_cache ]
        self._trove_cache.update(dict(itertools.izip(uncached,
            self._repos.getTroves(uncached))))

        # Cache config properties.
        self._populatePropertiesCache(nvfs)

        out = {}
        for nvf in sorted(nvfs, cmp=_srt_by_name):
            out[nvf] = self._getDescriptor(nvf)

        return out

    def _getDescriptor(self, nvf):
        if nvf in self._desc_cache:
            return self._desc_cache.get(nvf)

        subDescs = self._getDescriptorFromTrove(nvf)
        desc = self._populateDescriptor(subDescs)

        self._desc_cache[nvf] = desc

        if not subDescs:
            return ''

        return desc

    def _getDescriptorFromTrove(self, nvf):
        # Get properties from the repository
        properties = self._getProperties(nvf)
        nvfs = sorted(properties, key=lambda a: a.name)

        descs = []
        for nvf in nvfs:
            # use cached copy
            if nvf in self._desc_cache:
                desc = self._desc_cache.get(nvf)
                descs.append((nvf.name, desc))
                continue

            # if properties is None, then this nvf has no properties.
            propSet = properties.get(nvf)

            desc = self._loadDescriptorFromProperties(nvf, propSet)

            descs.append((nvf.name, desc))
            self._desc_cache[nvf] = desc

        return descs

    def _getProperties(self, nvf):
        return dict((x, self._properties_cache.get(x))
            for x in self._bydefault.get(nvf)
                if x in self._properties_cache)

    def _populatePropertiesCache(self, nvfs):
        specs = set()
        for nvf in nvfs:
            if nvf not in self._bydefault:
                trv = self._trove_cache.get(nvf)

                # Get all byDefault=True troves in name order.
                bydefault = set(TroveTuple(x)
                    for x, y, _ in trv.iterTroveListInfo() if y)
                self._bydefault[nvf] = bydefault
            else:
                bydefault = self._bydefault.get(nvf)

            specs |= bydefault

        # Filter out any nvfs that are already cached.
        req = [ x for x in specs if x not in self._properties_cache ]

        # Get properties from the repository.
        if not isinstance(self._repos, Database):
            properties = self._repos.getTroveInfo(_TROVEINFO_TAG_PROPERTIES, req)
            resp = ((x, y) for x, y in itertools.izip(req, properties) if y)
        else:
            resp = ((x, trove.PropertySet(y)) for (x, y) in
                    self._repos.db.getAllTroveInfo(_TROVEINFO_TAG_PROPERTIES))
        self._properties_cache.update(resp)

    def _loadDescriptorFromProperties(self, nvf, propSet):
        descs = []
        for prop in propSet.iter():
            xml = prop.definition()
            desc = SystemConfigurationDescriptor()

            try:
                desc.parseStream(StringIO(xml))

            # Ignore any descriptors that don't parse.
            except descriptor_errors.Error:
                continue

            descs.append(desc)

        # There was a descriptor, but it didn't parse.
        if not descs:
            log.error('failed to parse descriptor for %s' % (nvf, ))
            return

        # Only one descriptor was found for this nvf, no need to wrap it
        # in a complex data type.
        elif len(descs) == 1:
            desc = descs[0]

        # More than one descriptor was found for this nvf, wrap it in a
        # complex data type.
        else:
            desc = self._populateDescriptor([ (nvf.name, x) for x in descs ])

        return desc

    def _populateDescriptor(self, descs):
        desc = SystemConfigurationDescriptor()

        fields = {}
        sections = {}
        for name, subDesc in descs:
            if ':' in name:
                name = name.split(':')[0]
            for field in subDesc.getDataFields():
                section = field.get_section()
                if section:
                    sections.setdefault(section.get_key(), list()).append(field)
                else:
                    section = desc.xmlFactory().sectionTypeSub.factory()
                    section.set_key(name)
                    field.set_section(section)
                    fields.setdefault(name, list()).append(field)

        df = desc.getDataFields()
        df.extend(itertools.chain(*
            [ y for x, y in sorted(fields.iteritems(), key=lambda x: x[0]) ]))
        df.extend(itertools.chain(*
            [ y for x, y in sorted(sections.iteritems(), key=lambda x: x[0]) ]))

        return desc


if __name__ == '__main__':
    import sys
    from conary.lib import util
    sys.excepthook = util.genExcepthook()

    from conary import conarycfg
    from conary import conaryclient

    cfg = conarycfg.ConaryConfiguration(True)
    client = conaryclient.ConaryClient(cfg)

    cache = ConfigDescriptorCache(client.repos)

    specs = sorted(client.repos.findTrove(None,
        ('group-os', 'rhel.rpath.com@rpath:rhel-5-server', None),
        getLeaves=False))

    specs = specs[-50:]

    cache.getDescriptors(specs)

    #import epdb; epdb.st()
