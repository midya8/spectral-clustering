"""Check the installed tests and full CLI outputs outside the checkout.

Use --section tests or --section commands to run either half on its own.
The default runs both. These are same-runtime packaging comparisons, not
independent numerical or statistical evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV.pop('PYTHONPATH', None)
ENV.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
MODULES = ['spectrallab', 'spectrallab.__main__', 'spectrallab.core',
           'spectrallab.data', 'spectrallab.report', 'spectrallab.sensitivity']
COMMANDS = [
    ['spectrallab', 'fit', '--output', 'fresh.json'],
    ['spectrallab', 'audit', 'fresh.json'],
    ['spectrallab', 'audit', 'examples/report.json'],
    ['spectrallab', 'export', 'fresh.json', '--output', 'fresh-web'],
    ['spectrallab', 'export', 'examples/report.json', '--output', 'archived-web'],
    ['spectrallab.sensitivity', 'build', 'sensitivity-fresh.json'],
    ['spectrallab.sensitivity', 'audit', 'sensitivity-fresh.json'],
    ['spectrallab.sensitivity', 'audit', 'examples/sensitivity.json'],
    ['spectrallab.sensitivity', 'export', 'examples/sensitivity.json'],
]
REPORTS = ['fresh.json', 'sensitivity-fresh.json']
EXPORTS = [folder + '/' + name + '.js'
           for folder in ['fresh-web', 'archived-web']
           for name in ['moons', 'circles', 'data']]


def call(args, cwd, env=ENV):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--section', choices=['all', 'tests', 'commands'], default='all')
args = parser.parse_args()
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    wheels = work / 'wheels'
    wheels.mkdir()
    call([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '-w', str(wheels), str(ROOT)], work)
    built = list(wheels.glob('*.whl'))
    assert len(built) == 1, built
    venv.create(work / 'env', with_pip=True)
    py = str(work / 'env/bin/python')
    call([py, '-m', 'pip', 'install', str(built[0])], work)
    outside = work / 'outside'
    outside.mkdir()
    for name in ['tests', 'examples', 'docs']:
        shutil.copytree(ROOT / name, outside / name)
    suite = '''
import importlib,importlib.util,json,pathlib,sys,unittest
outside=pathlib.Path.cwd().resolve()
sys.path.insert(0,str(outside))
names=json.loads(sys.argv[1])
source=pathlib.Path(sys.argv[2]).resolve()
prefix=pathlib.Path(sys.prefix).resolve()
for name in names:importlib.import_module(name)
def check():
    for name in names:
        origin=pathlib.Path(importlib.util.find_spec(name).origin).resolve()
        assert origin.is_relative_to(prefix),(name,str(origin))
        assert not origin.is_relative_to(source),(name,str(origin))
        assert 'site-packages' in origin.parts,(name,str(origin))
check()
if sys.argv[3]=='tests':
    tests=unittest.defaultTestLoader.discover(str(outside/'tests'))
    result=unittest.TextTestRunner(verbosity=2).run(tests)
    assert result.testsRun>0 and result.wasSuccessful()
    print(json.dumps(dict(tests=result.testsRun)))
check()
print(json.dumps(dict(installed_origins=len(names),checked_before_and_after=True)))
'''
    if args.section in ['all', 'tests']:
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'tests'], outside))
    if args.section in ['all', 'commands']:
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'imports'], outside))
        reference = work / 'reference'
        reference.mkdir()
        shutil.copytree(ROOT / 'examples', reference / 'examples')
        source_env = ENV.copy()
        source_env['PYTHONPATH'] = str(ROOT)
        expected = []
        for command in COMMANDS:
            output = call([sys.executable, '-m'] + command, reference, source_env).strip()
            expected.append(output)
        reports = {name: json.loads((reference / name).read_text()) for name in REPORTS}
        exports = {name: (reference / name).read_bytes() for name in EXPORTS}
        for command, report in zip(COMMANDS, expected):
            output = call([py, '-I', '-m'] + command, outside).strip()
            assert output == report, command
        for name, report in reports.items():
            assert json.loads((outside / name).read_text()) == report, name
        for name, data in exports.items():
            assert (outside / name).read_bytes() == data, name
        for name in ['moons', 'circles', 'data']:
            assert exports['archived-web/' + name + '.js'] == (ROOT / 'docs' / (name + '.js')).read_bytes()
        assert expected[-1].encode() + b'\n' == (ROOT / 'docs/sensitivity-data.js').read_bytes()
        print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT), 'imports'], outside))
        print(json.dumps(dict(command_invocations=len(COMMANDS), command_kinds=6,
                              complete_output_files=8, fresh_graph_fits=18,
                              sensitivity_cases=6, module_entrypoints=2)))
