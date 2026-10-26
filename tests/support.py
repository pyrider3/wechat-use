"""Render portable templates in a temporary installation for isolated tests."""
import importlib.util, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory(prefix='wechat-use-test-')
BUILD = pathlib.Path(TEMP.name)
spec = importlib.util.spec_from_file_location('installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
for source in (ROOT / 'templates').glob('*.py'):
    (BUILD / source.name).write_text(installer.render(source.read_text(), BUILD / 'home', BUILD, BUILD / 'runtime'))
sys.path.insert(0, str(BUILD))
def load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, BUILD / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
