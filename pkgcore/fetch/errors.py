# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
errors fetch subsystem may throw
"""

class base(Exception):
    pass

class distdirPerms(base):
    def __init__(self, distdir, required):
        base.__init__(
            self, "distdir '%s' required fs attributes weren't enforcable: %s"
            % (distdir, required))
        self.distdir, self.required = distdir, required

class UnmodifiableFile(base):
    def __init__(self, filename, extra=''):
        base.__init__(self, "Unable to update file %s, unmodifiable %s"
                      % (filename, extra))
        self.file = filename

class UnknownMirror(base):
    def __init__(self, host, uri):
        base.__init__(self, "uri mirror://%s/%s is has no known mirror tier"
                      % (host, uri))
        self.host, self.uri = host, uri

class RequiredChksumDataMissing(base):
    def __init__(self, fetchable, chksum):
        base.__init__(self, "chksum %s was configured as required, "
                      "but the data is missing from fetchable '%s'"
                      % (chksum, fetchable))
        self.fetchable, self.missing_chksum = fetchable, chksum
