# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
gentoo/ebuild specific triggers
"""

from pkgcore.merge import triggers
from pkgcore.util.file import read_bash_dict, AtomicWriteFile
from pkgcore.fs import util, livefs
from pkgcore.util.currying import pre_curry
from pkgcore.restrictions import values
import os, errno, stat

colon_parsed = set(
    ["ADA_INCLUDE_PATH",  "ADA_OBJECTS_PATH", "LDPATH", "MANPATH",
     "PATH", "PRELINK_PATH", "PRELINK_PATH_MASK", "PYTHONPATH",
     "PKG_CONFIG_PATH"])

incrementals = set(
    ['ADA_INCLUDE_PATH', 'ADA_OBJECTS_PATH', 'CLASSPATH', 'CONFIG_PROTECT',
     'CONFIG_PROTECT_MASK', 'INFODIR', 'INFOPATH', 'KDEDIRS', 'LDPATH',
     'MANPATH', 'PATH', 'PRELINK_PATH', 'PRELINK_PATH_MASK', 'PYTHONPATH',
     'ROOTPATH', 'PKG_CONFIG_PATH'])

def collapse_envd(base):
    pjoin = os.path.join
    collapsed_d = {"LDPATH":["/usr/lib"]}
    for x in sorted(os.listdir(base)):
        if (x.endswith(".bak") or x.endswith("~") or x.startswith("._cfg")
            or not (len(x) > 2 and x[0:2].isdigit()
                    and stat.S_ISREG(os.lstat(pjoin(base, x)).st_mode))):
            continue
        d = read_bash_dict(pjoin(base, x))
        # inefficient, but works.
        for k in d:
            if k in incrementals:
                if k in colon_parsed:
                    collapsed_d.setdefault(k, []).extend(d[k].split(":"))
                else:
                    collapsed_d.setdefault(k, []).append(d[k])
            else:
                collapsed_d[k] = d[k]
        del d
    return collapsed_d


def raw_env_update(engine, cset):
    pjoin = os.path.join
    offset = engine.offset
    collapsed_d = collapse_envd(pjoin(offset, "etc/env.d"))

    if "LDPATH" in collapsed_d:
        # we do an atomic rename instead of open and write quick
        # enough (avoid the race iow)
        fp = pjoin(offset, "etc", "ld.so.conf")
        new_f = AtomicWriteFile(fp)
        new_f.write("# automatically generated, edit env.d files instead\n")
        new_f.writelines(x.strip()+"\n" for x in collapsed_d["LDPATH"])
        new_f.close()
        del collapsed_d["LDPATH"]

    d = {}
    for k, v in collapsed_d.iteritems():
        if k in incrementals:
            if k in colon_parsed:
                d[k] = ":".join(v)
            else:
                d[k] = v[-1]
        else:
            d[k] = v

    new_f = AtomicWriteFile(pjoin(offset, "etc", "profile.env"))
    new_f.write("# autogenerated.  update env.d instead\n")
    new_f.writelines('export %s="%s"\n' % (k, d[k]) for k in sorted(d))
    new_f.close()
    new_f = AtomicWriteFile(pjoin(offset, "etc", "profile.csh"))
    new_f.write("# autogenerated, update env.d instead\n")
    new_f.writelines('setenv %s="%s"\n' % (k, d[k]) for k in sorted(d))
    new_f.close()


def env_update_trigger(cset="install"):
    return triggers.SimpleTrigger(cset, raw_env_update)


def simple_chksum_compare(x, y):
    found = False
    for k, v in x.chksums.iteritems():
        if k == "size":
            continue
        o = y.chksums.get(k, None)
        if o is not None:
            if o != v:
                return False
            found = True
    if "size" in x.chksums and "size" in y.chksums:
        return x.chksums["size"] == y.chksums["size"]
    return found


def gen_config_protect_filter(offset):
    collapsed_d = collapse_envd(os.path.join(offset, "etc/env.d"))

    r = [values.StrGlobMatch(util.normpath(x).rstrip("/") + "/")
         for x in set(collapsed_d.get("CONFIG_PROTECT", []) + ["/etc"])]
    if len(r) > 1:
        r = values.OrRestriction(*r)
    else:
        r = r[0]
    neg = collapsed_d.get("CONFIG_PROTECT_MASK", None)
    if neg is not None:
        if len(neg) == 1:
            r2 = values.StrGlobMatch(util.normpath(neg[0]).rstrip("/") + "/",
                                     negate=True)
        else:
            r2 = values.OrRestriction(
                negate=True,
                *[values.StrGlobMatch(util.normpath(x).rstrip("/") + "/")
                  for x in set(neg)])
        r = values.AndRestriction(r, r2)
    return r


def config_protect_func_install(existing_cset, install_cset, engine, csets):
    install_cset = csets[install_cset]
    existing_cset = csets[existing_cset]

    pjoin = os.path.join
    offset = engine.offset

    # hackish, but it works.
    protected_filter = gen_config_protect_filter(engine.offset).match
    protected = {}

    for x in existing_cset.iterfiles():
        if x.location.endswith("/.keep"):
            continue
        elif protected_filter(x.location):
            replacement = install_cset[x]
            if not simple_chksum_compare(replacement, x):
                protected.setdefault(
                    pjoin(engine.offset,
                          os.path.dirname(x.location).lstrip(os.path.sep)),
                    []).append((os.path.basename(replacement.location),
                                replacement))

    for dir_loc, entries in protected.iteritems():
        updates = dict((x[0], []) for x in entries)
        try:
            existing = sorted(x for x in os.listdir(dir_loc)
                              if x.startswith("._cfg"))
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
            # this shouldn't occur.
            continue

        for x in existing:
            try:
                # ._cfg0000_filename
                count = int(x[5:9])
                if x[9] != "_":
                    raise ValueError
                fn = x[10:]
            except (ValueError, IndexError):
                continue
            if fn in updates:
                updates[fn].append((count, fn))


        # now we rename.
        for fname, entry in entries:
            # check for any updates with the same chksums.
            count = 0
            for cfg_count, cfg_fname in updates[fname]:
                if simple_chksum_compare(livefs.gen_obj(
                        pjoin(dir_loc, cfg_fname)), entry):
                    count = cfg_count
                    break
                count = max(count, cfg_count + 1)
            try:
                install_cset.remove(entry)
            except KeyError:
                # this shouldn't occur...
                continue
            new_fn = pjoin(dir_loc, "._cfg%02i_%s" % (count, fname))
            install_cset.add(entry.change_attributes(real_location=new_fn))
        del updates


def config_protect_trigger_install(existing_cset="install_existing",
                                   modifying_cset="install"):
    return triggers.trigger([existing_cset, modifying_cset],
                            pre_curry(config_protect_func_install,
                                      existing_cset, modifying_cset))


def config_protect_func_uninstall(existing_cset, uninstall_cset, engine, csets):
    uninstall_cset = csets[uninstall_cset]
    existing_cset = csets[existing_cset]
    pjoin = os.path.join
    protected_restrict = gen_config_protect_filter(engine.offset)

    remove = []
    for x in existing_cset.iterfiles():
        if x.location.endswith("/.keep"):
            continue
        if protected_restrict.match(x.location):
            recorded_ent = uninstall_cset[x]
            if not simple_chksum_compare(recorded_ent, x):
                # chksum differs.  file stays.
                remove.append(recorded_ent)
    
    for x in remove:
        del uninstall_cset[x]


def config_protect_trigger_uninstall(existing_cset="uninstall_existing",
                                     modifying_cset="uninstall"):
    return triggers.trigger([existing_cset, modifying_cset],
                            pre_curry(config_protect_func_uninstall,
                                      existing_cset, modifying_cset))

def preinst_contents_reset_func(format_op, engine, cset):
    # wipe, and get data again.
    cset.clear()
    cset.update(engine.new._parent.scan_contents(format_op.env["D"]))

def preinst_contents_reset_register(trigger, hook_name, triggers_list):
    for x in triggers_list:
        if x.label == "preinst_contents_reset":
            break
    else:
        triggers_list.insert(0, trigger)

def preinst_contents_reset_trigger(format_op):
    return triggers.SimpleTrigger("install", 
        pre_curry(preinst_contents_reset_func, format_op),
        register_func=preinst_contents_reset_register,
        label="preinst_contents_reset")
