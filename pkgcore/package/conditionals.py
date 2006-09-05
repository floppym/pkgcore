# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
conditional attributes on a package, changing them triggering regen of other attributes on the package instance
"""

from pkgcore.util.containers import LimitedChangeSet, Unchangable
from pkgcore.util.demandload import demandload
demandload(globals(), "copy")

class PackageWrapper(object):

    """wrap a package instance adding a new attribute, and evaluating the wrapped pkgs attributes"""

    def __init__(self, pkg_instance, configurable_attribute_name,
                 initial_settings=None, unchangable_settings=None,
                 attributes_to_wrap=None, build_callback=None):

        """
        @param pkg_instance: L{pkgcore.package.metadata.package} instance to wrap
        @param configurable_attribute_name: attribute name to add, and that is used for evaluating attributes_to_wrap
        @param initial_settings: sequence, initial configuration of the configurable_attribute
        @param unchangable_settings: sequence, settings that configurable_attribute cannot be set to
        @param attributes_to_wrap: mapping of attr_name:callable for revaluating the pkg_instance, using the result instead of the wrapped pkgs attr
        @param build_callback: None, or a callable to be used to get a L{pkgcore.interfaces.build.base} instance
        """

        if initial_settings is None:
            initial_settings = []
        if unchangable_settings is None:
            unchangable_settings = []
        self._raw_pkg = pkg_instance
        if attributes_to_wrap is None:
            attributes_to_wrap = {}
        self._wrapped_attr = attributes_to_wrap
        if configurable_attribute_name.find(".") != -1:
            raise ValueError("can only wrap first level attributes, "
                             "'obj.dar' fex, not '%s'" %
                             (configurable_attribute_name))
        setattr(self, configurable_attribute_name,
                LimitedChangeSet(initial_settings, unchangable_settings))
        self._unchangable = unchangable_settings
        self._configurable = getattr(self, configurable_attribute_name)
        self._configurable_name = configurable_attribute_name
        self._reuse_pt = 0
        self._cached_wrapped = {}
        self._buildable = build_callback

    def __copy__(self):
        return self.__class__(self._raw_pkg, self._configurable_name,
                              initial_settings=set(self._configurable),
                              unchangable_settings=self._unchangable,
                              attributes_to_wrap=self._wrapped_attr)

    def rollback(self, point=0):
        """
        rollback changes to the configurable attribute to an earlier point

        @param point: must be an int
        """
        self._configurable.rollback(point)
        # yes, nuking objs isn't necessarily required.  easier this way though.
        # XXX: optimization point
        self._reuse_pt += 1

    def commit(self):
        """
        commit current changes, this means that those those changes can be reverted from this point out
        """
        self._configurable.commit()
        self._reuse_pt = 0

    def changes_count(self):
        """
        current commit point for the configurable
        """
        return self._configurable.changes_count()

    def request_enable(self, attr, *vals):
        """
        internal function

        since configurable somewhat steps outside of normal
        restriction protocols, request_enable requests that this
        package instance change its configuration to make the
        restriction return True; if not possible, reverts any changes
        it attempted

        @param attr: attr to try and change
        @param vals: L{pkgcore.restrictions.values.base} instances that we're attempting to make match True
        """
        if attr not in self._wrapped_attr:
            if attr == self._configurable_name:
                entry_point = self.changes_count()
                try:
                    map(self._configurable.add, vals)
                    self._reuse_pt += 1
                    return True
                except Unchangable:
                    self.rollback(entry_point)
            else:
                a = getattr(self._raw_pkg, attr)
                for x in vals:
                    if x not in a:
                        break
                else:
                    return True
            return False
        entry_point = self.changes_count()
        a = getattr(self._raw_pkg, attr)
        try:
            for x in vals:
                succeeded = False
                for reqs in a.node_conds.get(x, []):
                    succeeded = reqs.force_true(self)
                    if succeeded:
                        break
                if not succeeded:
                    self.rollback(entry_point)
                    return False
        except Unchangable:
            self.rollback(entry_point)
            return False
        self._reuse_pt += 1
        return True

    def request_disable(self, attr, *vals):
        """
        internal function

        since configurable somewhat steps outside of normal
        restriction protocols, request_disable requests that this
        package instance change its configuration to make the
        restriction return False; if not possible, reverts any changes
        it attempted

        @param attr: attr to try and change
        @param vals: L{pkgcore.restrictions.values.base} instances that we're attempting to make match False
        """
        if attr not in self._wrapped_attr:
            if attr == self._configurable_name:
                entry_point = self.changes_count()
                try:
                    map(self._configurable.remove, vals)
                    return True
                except Unchangable:
                    self.rollback(entry_point)
            else:
                a = getattr(self._raw_pkg, attr)
                for x in vals:
                    if x in a:
                        break
                else:
                    return True
            return False
        entry_point = self.changes_count()
        a = getattr(self._raw_pkg, attr)
        try:
            for x in vals:
                succeeded = False
                for reqs in a.node_conds.get(x, []):
                    succeeded = reqs.force_false(self)
                    if succeeded:
                        break
                if not succeeded:
                    self.rollback(entry_point)
                    return False
        except Unchangable:
            self.rollback(entry_point)
            return False
        self._reuse_pt += 1
        return True

    def __getattr__(self, attr):
        if attr in self._wrapped_attr:
            if attr in self._cached_wrapped:
                if self._cached_wrapped[attr][0] == self._reuse_pt:
                    return self._cached_wrapped[attr][1]
                del self._cached_wrapped[attr]
            o = self._wrapped_attr[attr](getattr(self._raw_pkg, attr),
                                         self._configurable)
            self._cached_wrapped[attr] = (self._reuse_pt, o)
            return o
        else:
            return getattr(self._raw_pkg, attr)

    def __str__(self):
#        return "config wrapper: %s, configurable('%s'):%s" % (
#            self._raw_pkg, self._configurable_name, self._configurable)
        return "config wrapped(%s): %s" % (self._configurable_name,
                                           self._raw_pkg)

    def __repr__(self):
        return "<%s pkg=%r wrapped=%r @%#8x>" % (
            self.__class__.__name__, self._raw_pkg, self._configurable_name,
            id(self))

    def freeze(self):
        o = copy.copy(self)
        o.lock()
        return o

    def lock(self):
        """
        commit any outstanding changes, and lock the configuration so that it's unchangable.
        """
        self.commit()
        self._configurable = list(self._configurable)

    def build(self):
        if self._buildable:
            return self._buildable(self)
        return None

    def __cmp__(self, other):
        if isinstance(other, PackageWrapper):
            if isinstance(other._raw_pkg, self._raw_pkg.__class__):
                c = cmp(self._raw_pkg, other._raw_pkg)
                if c:
                    return c
                if self._configurable == other._configurable:
                    return 0
                # sucky, but comparing sets isn't totally possible.
                # potentially do sub/super tests instead?
                raise TypeError
        elif isinstance(other, self._raw_pkg.__class__):
            return cmp(self._raw_pkg, other)
        else:
            c = cmp(other, self)
            if c == 0:
                return 0
            return -c
        raise NotImplementedError

    def __eq__(self, other):
        if isinstance(other, PackageWrapper):
            if self._raw_pkg == other._raw_pkg:
                return self._configurable == other._configurable
            return False
        elif isinstance(other, self._raw_pkg.__class__):
            return self._raw_pkg == other
        return False
