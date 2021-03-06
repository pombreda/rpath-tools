#!/bin/sh
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


basicAuth=$(grep ^doBasicAuth: /etc/sfcb/sfcb.cfg | awk '{print $2}')
if [ x"$basicAuth" != xfalse ]; then
        sed -i 's/doBasicAuth:\([[:space:]]*\).*$/doBasicAuth:\1false/' /etc/sfcb/sfcb.cfg
        /etc/init.d/sfcb condrestart
fi

/usr/sbin/vmware-guestd --cmd 'info-set guestinfo.vmware.vami.version 0.1' > /dev/null
/usr/sbin/vmware-guestd --cmd 'info-set guestinfo.vmware.vami.features SUP' > /dev/null
/usr/sbin/vmware-guestd --cmd 'info-set guestinfo.vmware.vami.https-port 5989' > /dev/null
