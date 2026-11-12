"""Build exact packet-profile resources from the one canonical source family."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

PACKET_PROFILES = (
    'packet-return.schema.json', 'packet-return.v2.schema.json',
    'packet-judgement.schema.json', 'packet-judgement.v2.schema.json',
)


class build_py(_build_py):
    def run(self):
        canonical = Path(__file__).resolve().parent / 'profiles' / 'workflows'
        for name in PACKET_PROFILES:
            if not (canonical / name).is_file():
                raise FileNotFoundError('Missing canonical packet profile: ' + str(canonical / name))
        super().run()
        destination = Path(self.build_lib) / 'laplace' / 'pipeline' / 'packet_profiles'
        self.mkpath(str(destination))
        for name in PACKET_PROFILES:
            self.copy_file(str(canonical / name), str(destination / name))

    def get_outputs(self, include_bytecode=1):
        generated = [str(Path(self.build_lib) / 'laplace' / 'pipeline' / 'packet_profiles' / name)
                     for name in PACKET_PROFILES]
        return list(dict.fromkeys([*super().get_outputs(include_bytecode), *generated]))


setup(cmdclass={'build_py': build_py})
