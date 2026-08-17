#!/usr/bin/env python3
"""licgen — générateur de codes de licence AMI.

Exemples :
    python licgen.py                 # 1 code
    python licgen.py -n 5            # 5 codes
    python licgen.py --name "Client" # avec un libellé client (informatif)
    python licgen.py --check AMI-XXXX-XXXX-XXXX-XXXX   # vérifier un code
"""
import argparse

from admi.license import generate_license, verify_license


def main():
    ap = argparse.ArgumentParser(description="Générateur de licences AMI")
    ap.add_argument("-n", "--count", type=int, default=1, help="nombre de codes à générer")
    ap.add_argument("-N", "--name", default="", help="nom du client (informatif)")
    ap.add_argument("--check", metavar="CODE", help="vérifier la validité d'un code")
    args = ap.parse_args()

    if args.check:
        ok = verify_license(args.check)
        print(f"{args.check} : {'VALIDE' if ok else 'INVALIDE'}")
        raise SystemExit(0 if ok else 1)

    if args.name:
        print(f"# Licences AMI pour : {args.name}")
    for _ in range(max(1, args.count)):
        code = generate_license()
        assert verify_license(code)
        print(code)


if __name__ == "__main__":
    main()
