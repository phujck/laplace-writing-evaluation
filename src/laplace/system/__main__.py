"""python -m laplace.system {check | owner PATH... | cone PATH... | capability ID | front-door [--write]} : one JSON answer on stdout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from laplace import system


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m laplace.system', description=system.__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, default=None, help='repository root (default: the serving checkout)')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='every claimed relationship measured against the tree')
    owners = commands.add_parser('owner', help='the one owning subsystem of each path')
    owners.add_argument('paths', nargs='+')
    cones = commands.add_parser('cone', help='the affected cone of a change to these paths')
    cones.add_argument('paths', nargs='+')
    cones.add_argument('--depth', type=int, default=2)
    capabilities = commands.add_parser('capability', help='one operation-bearing capability, resolved')
    capabilities.add_argument('id')
    front = commands.add_parser('front-door', help='the generated subsystem section of the human front door')
    front.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    root = (args.root or system.repository_root()).resolve()
    description = system.load()
    if args.command == 'check':
        result = system.check(root, description)
    elif args.command == 'owner':
        result = {path: dict(zip(('subsystem', 'problem'), system.owner(description, path))) for path in args.paths}
    elif args.command == 'cone':
        result = system.cone(root, args.paths, description, depth=args.depth)
    elif args.command == 'front-door':
        result = {'changed': system.write_front_door(root, description)} if args.write else {'section': system.render_front_door(description)}
    else:
        result = system.capability(args.id, description, root)
    json.dump(result, sys.stdout, indent=1, sort_keys=True, default=str)
    sys.stdout.write('\n')
    return 0 if args.command != 'check' or result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
