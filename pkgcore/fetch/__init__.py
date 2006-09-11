# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
functionality related to downloading files
"""

class fetchable(object):

    """class representing uri sources for a file and chksum information."""

    __slots__ = ("filename", "uri", "chksums")

    def __init__(self, filename, uri=None, chksums=None):
        """
        @param filename: filename...
        @param uri: either None (no uri),
            or a sequence of uri where the file is available
        @param chksums: either None (no chksum data),
            or a dict of chksum_type -> value for this file
        """
        self.uri = uri
        if chksums is None:
            self.chksums = {}
        else:
            self.chksums = chksums
        self.filename = filename

    def __str__(self):
        return "('%s', '%s', (%s))" % (
            self.filename, self.uri, ', '.join(self.chksums))


class mirror(object):
    """
    uri source representing a mirror tier
    """
    __slots__ = ("mirrors", "mirror_name")

    def __init__(self, mirrors, mirror_name):
        """
        @param uri: the uri to try accessing per mirror server
        @param mirrors: list of hosts that comprise this mirror tier
        @param mirror_name: name of the mirror tier
        """

        if not isinstance(mirrors, tuple):
            mirrors = tuple(mirrors)
        self.mirrors = mirrors
        self.mirror_name = mirror_name

    def __iter__(self):
        return iter(self.mirrors)

    def __str__(self):
        return "mirror://%s" % self.mirror_name

    def __len__(self):
        return len(self.mirrors)

    def __getitem__(self, idx):
        return self.mirrors[idx]

    def __repr__(self):
        return "<%s mirror tier=%r>" % (self.__class__, self.mirror_name)

class default_mirror(mirror):
    pass


class uri_list(object):

    __slots__ = ("_uri_source", "filename", "__weakref__")

    def __init__(self, filename):
        self._uri_source = []
        self.filename = filename
    
    def add_mirror(self, mirror_inst):
        if not isinstance(mirror_inst, mirror):
            raise TypeError("mirror must be a pkgcore.fetch.mirror instance")
        self._uri_source.append(mirror_inst)
    
    def add_uri(self, uri):
        self._uri_source.append(uri)
    
    def finalize(self):
        self._uri_source = tuple(self._uri_source)

    def __iter__(self):
        fname = self.filename
        for entry in self._uri_source:
            if isinstance(entry, basestring):
                yield entry
            else:
                for base_uri in entry:
                    yield "%s/%s" % (base_uri, fname)

    def __str__(self):
        return "file: %s, uri: %s" % (self.filename, 
            ', '.join(str(x) for x in self._uri_source))
