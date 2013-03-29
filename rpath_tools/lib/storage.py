#!/usr/bin/python2.4
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


import collections
import os
import uuid

from conary.lib import util

#{ Exception classes
class StorageError(Exception):
    """Base class for all exceptions in the C{storage} module"""

class InvalidKeyError(StorageError):
    """An invalid key was specified"""

class KeyNotFoundError(StorageError):
    """The specified key was not found"""
#}

class BaseStorage(object):
    """
    Persistance class.
    cvar separator: separator between the class prefix and the key
    """
    separator = ','

    def __getitem__(self, key):
        """Get the value for the specified key.
        @param key: the key
        @type key: C{str}
        @rtype: C{str}
        @return: The value for the key, if set
        @raises InvalidKeyError: if the key was invalid
        @raises KeyNotFoundError: if the key is not set
        """
        key = self._sanitizeKey(key)
        if not self.exists(key):
            raise KeyNotFoundError(key)
        return self._real_get(key)

    def __setitem__(self, key, val):
        """Set the value for the specified key.
        @param key: the key
        @type key: C{str}
        @param val: value to store
        @type val: C{str}
        @raises InvalidKeyError: if the key was invalid
        """
        key = self._sanitizeKey(key)
        return self._real_set(key, val)

    def set(self, key, val):
        """Set the value for the specified key.
        @param key: the key
        @type key: C{str}
        @param val: value to store
        @type val: C{str}
        @raises InvalidKeyError: if the key was invalid
        """
        return self.__setitem__(key, val)

    def setFields(self, kvlist):
        for k, v in kvlist:
            if v is None:
                self.delete(k)
            else:
                self.set(k, v)

    def get(self, key, default = None):
        """Get the value for the specified key.
        @param key: the key
        @type key: C{str}
        @param default: a default value to be returned if the key is not set
        @type default: C{str}
        @rtype: C{str}
        @return: The value for the key, if set, or the value of C{default}
        @raises InvalidKeyError: if the key was invalid
        """
        if not self.exists(key):
            return default
        return self.__getitem__(key)

    def newCollection(self, key = None, keyPrefix = None):
        """Create collection"""
        if key is None:
            key = self.newKey(keyPrefix = keyPrefix)
        else:
            key = self._sanitizeKey(key)
        self._real_new_collection(key)
        return key

    def enumerate(self, keyPrefix = None):
        """Enumerate keys"""
        if keyPrefix is not None:
            keyPrefix = self._sanitizeKey(keyPrefix)
        return self._real_enumerate(keyPrefix)

    def enumerateAll(self, keyPrefix = None):
        """Enumerate all keys"""
        stack = collections.deque()
        stack.extend(self.enumerate(keyPrefix = keyPrefix))
        while stack:
            key = stack.popleft()
            if not self.isCollection(key):
                yield key
                continue
            stack.extendleft(self.enumerate(keyPrefix = key))

    def exists(self, key):
        """Check for a key's existance
        @param key: the key
        @type key: C{str}
        @rtype: C{bool}
        @return: True if the key exists, False otherwise
        """
        key = self._sanitizeKey(key)
        return self._real_exists(key)

    def isCollection(self, key):
        key = self._sanitizeKey(key)
        return self._real_is_collection(key)

    def newKey(self, keyPrefix = None):
        if isinstance(keyPrefix, tuple):
            keyPrefix = list(keyPrefix)
        elif keyPrefix is not None:
            keyPrefix = [ keyPrefix ]
        for i in range(5):
            newKey = self._generateString()
            if keyPrefix is not None:
                key = self.separator.join(keyPrefix +  [newKey])
            else:
                key = newKey
            if not self.exists(key):
                return key

        raise StorageError("Failed to generate a new key")

    def store(self, val, keyPrefix = None):
        """Generate a new key, and store the value.
        @param val: value to store
        @type val: C{str}
        @param keyPrefix: a prefix to be prepended to the key
        @type keyPrefix: C{str}
        @return: The newly generated key
        @rtype: C{str}
        @raises StorageError: if the module was unable to generate a new key
        """
        key = self.newKey(keyPrefix = keyPrefix)
        self.set(key, val)
        return key

    def delete(self, key):
        """Delete a key
        @param key: the key
        @type key: C{str}
        @rtype: C{bool}
        @return: True if the key exists, False otherwise
        """
        key = self._sanitizeKey(key)
        if self.isCollection(key):
            return self._real_delete_collection(key)
        return self._real_delete(key)

    def getFileFromKey(self, key):
        key = self._sanitizeKey(key)
        return self._real_get_file_from_key(key)

    def commit(self):
        """
        Commit an entry
        """

    #{ Methods that could be overwritten in subclasses
    def _generateString(self):
        """Generate a string
        @rtype: C{str}
        @return: The new string
        """
        return str(uuid.uuid4())
    #}

    #{ Methods that should be overwritten in subclasses
    def _sanitizeKey(self, key):
        """Sanitize the key by removing potentially dangerous characters.
        @param key: key
        @type key: C{str}
        @rtype: C{str}
        @return: The sanitized key
        @raises InvalidKeyError: if the key was invalid
        """

    def _real_get(self, key):
        raise NotImplementedError()

    def _real_set(self, key, val):
        raise NotImplementedError()

    def _real_exists(self, key):
        raise NotImplementedError()

    def _real_delete(self, key):
        raise NotImplementedError()

    def _real_new_collection(self, key):
        raise NotImplementedError()

    def _real_delete_collection(self, key):
        raise NotImplementedError()

    def _real_enumerate(self, keyPrefix):
        raise NotImplementedError()

    def _real_is_collection(self, key):
        raise NotImplementedError()

    def _real_get_file_from_key(self, key):
        raise NotImplementedError()
    #}

class DiskStorage(BaseStorage):
    separator = os.sep

    def __init__(self, cfg):
        """Constructor
        @param cfg: Configuration object
        @type cfg: C{StorageConfig}
        """
        self.cfg = cfg

    def _sanitizeKey(self, key):
        key = self._collapsePrefixes(key)
        nkey = os.path.normpath(key)
        if key != nkey:
            raise InvalidKeyError(key)
        if key[0] == self.separator:
            raise InvalidKeyError(key)
        return key

    def _collapsePrefixes(self, prefixes):
        # Recursively join prefixes using the separator
        if not isinstance(prefixes, tuple):
            return prefixes
        return self.separator.join(
            self._collapsePrefixes(x) for x in prefixes)

    def _real_get(self, key):
        fpath = self._getFileForKey(key)
        return file(fpath).read()

    def _real_set(self, key, val):
        fpath = self._getFileForKey(key, createDirs = True)
        file(fpath, "w").write(str(val))
        return fpath

    def _real_exists(self, key):
        fpath = self._getFileForKey(key)
        return os.path.exists(fpath)

    def _real_delete(self, key):
        fpath = self._getFileForKey(key)
        if os.path.exists(fpath):
            os.unlink(fpath)

    def _real_new_collection(self, key):
        fpath = self._getFileForKey(key)
        util.mkdirChain(fpath)
        return fpath

    def _real_delete_collection(self, key):
        fpath = self._getFileForKey(key)
        util.rmtree(fpath, ignore_errors = True)

    def _real_enumerate(self, keyPrefix = None):
        if keyPrefix is None:
            collection = self.cfg.storagePath
        else:
            # Get rid of trailing /
            keyPrefix = keyPrefix.rstrip(self.separator)
            collection = self.separator.join([self.cfg.storagePath, keyPrefix])
        if not os.path.isdir(collection):
            return []
        dirContents = sorted(os.listdir(collection))
        if keyPrefix is None:
            return dirContents
        return sorted([ self.separator.join([keyPrefix, x]) for x in dirContents ])

    def _real_is_collection(self, key):
        collection = self.separator.join([self.cfg.storagePath, key])
        return os.path.isdir(collection)

    def _getFileForKey(self, key, createDirs = False):
        ret = self.separator.join([self.cfg.storagePath, key])
        if createDirs:
            util.mkdirChain(os.path.dirname(ret))
        return ret

    _real_get_file_from_key = _getFileForKey

class StorageConfig(object):
    """
    Storage configuration object.
    @ivar storagePath: Path used for persisting the values.
    @type storagePath: C{str}
    """
    def __init__(self, storagePath):
        self.storagePath = storagePath
