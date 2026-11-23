"""Keep linker response-file paths relative: old MinGW ld mishandles Czech paths."""
Import('env')
root = env.subst('$PROJECT_DIR').replace('\\', '/') + '/'
env.Replace(LINKFLAGS=[env.subst(str(item)).replace('\\', '/').replace(root, '') for item in env['LINKFLAGS']])
paths = [env.subst(str(item)).replace('\\', '/') for item in env['LIBPATH']]
env.Replace(LIBPATH=[env.Dir('#' + path[len(root):]) if path.startswith(root) else path for path in paths])
