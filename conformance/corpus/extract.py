import glob, hashlib, json, os, re, sys
import xml.etree.ElementTree as ET
from html import unescape
root = os.path.expanduser('~/work/contiki-ng/tests')
out = {}
tests = []
for csc in sorted(glob.glob(root + '/*/*.csc')):
    rel = os.path.relpath(csc, root)
    tree = ET.parse(csc)
    script, src = None, None
    for plug in tree.getroot().iter('plugin'):
        if 'ScriptRunner' in (plug.text or ''):
            pc = plug.find('plugin_config')
            if pc is None: continue
            sf = pc.find('scriptfile'); sc = pc.find('script')
            if sf is not None and sf.text:
                path = sf.text.strip().replace('[CONFIG_DIR]', os.path.dirname(csc)).replace('[CONTIKI_DIR]', os.path.expanduser('~/work/contiki-ng'))
                src = os.path.relpath(path, root)
                script = open(path).read() if os.path.exists(path) else None
            elif sc is not None and sc.text:
                script, src = unescape(sc.text), 'inline'
    if script is None:
        tests.append({'test': rel, 'script': None, 'src': src}); continue
    norm = re.sub(r'/\*.*?\*/', '', script, flags=re.S)
    norm = re.sub(r'(?m)(^|\s)//.*$', '', norm)
    norm = re.sub(r'\s+', ' ', norm).strip()
    h = hashlib.sha1(norm.encode()).hexdigest()[:8]
    out.setdefault(h, {'script': script, 'tests': [], 'src': set()})
    out[h]['tests'].append(rel); out[h]['src'].add(src)
    tests.append({'test': rel, 'script': h, 'src': src})
for h in out: out[h]['src'] = sorted(out[h]['src'])
json.dump({'scripts': out, 'tests': tests}, open(sys.argv[1], 'w'), indent=1)
print(len(tests), 'tests,', len(out), 'unique scripts,', sum(1 for t in tests if t['script'] is None), 'without script')
for h, v in sorted(out.items(), key=lambda kv: -len(kv[1]['tests'])):
    print(h, len(v['tests']), 'tests', len(v['script'].splitlines()), 'lines', v['src'][:2])
