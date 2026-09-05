"""Export diagnostic STL parts from the *same* v3 source model. Never writes latest/."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from backend.app.fabrication import PrintPlan, PrintProfile, export_print_package


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True,help='building_model_v3.json, not GLB')
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--plan',type=Path,help='Explicit parts/exclusions; default groups by source level')
    parser.add_argument('--output',type=Path,required=True,help='New diagnostic directory (never overwrite)')
    parser.add_argument('--release',action='store_true',help='Fail closed until production verification is implemented')
    args=parser.parse_args(argv)
    try:
        model=json.loads(args.model.read_text(encoding='utf-8'))
        profile=PrintProfile.model_validate_json(args.profile.read_text(encoding='utf-8'))
        plan=PrintPlan.model_validate_json(args.plan.read_text(encoding='utf-8')) if args.plan else None
        report=export_print_package(model,profile,args.output,plan,release=args.release)
    except (OSError,ValueError,RuntimeError) as error:
        print(f'Print export blocked: {error}',file=sys.stderr); return 2
    print(json.dumps({'directory':str(args.output),'package_id':report['package_id'],
                      'verification':report['verification'],'release_ready':False},indent=2))
    # Diagnostic files remain inspectable, but a failed or unresolved gate is not success.
    return 0 if all(report['verification'][k]=='passed' for k in
                    ('geometry_verified','profile_screened')) else 2


if __name__=='__main__':
    raise SystemExit(main())
