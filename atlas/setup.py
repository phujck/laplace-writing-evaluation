"""Bundle the exact canonical synthetic ingestion fixture in the Atlas wheel."""
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

CANONICAL_FIXTURE = Path(__file__).resolve().parents[1] / 'evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py'


class build_py(_build_py):
    def run(self):
        if not CANONICAL_FIXTURE.is_file():
            raise FileNotFoundError('Missing declared Atlas toy input: ' + str(CANONICAL_FIXTURE))
        super().run()
        destination = Path(self.build_lib) / 'atlas/record/ingest/_toy_corpus.py'
        self.mkpath(str(destination.parent))
        self.copy_file(str(CANONICAL_FIXTURE), str(destination))

    def get_outputs(self, include_bytecode=1):
        resource = str(Path(self.build_lib) / 'atlas/record/ingest/_toy_corpus.py')
        return list(dict.fromkeys([*super().get_outputs(include_bytecode), resource]))


setup(cmdclass={'build_py': build_py})
