"""reelkit CLI.  python -m reelkit <comando> ...   (ver README.md)"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser(prog="reelkit", description="Edición de Reels desde entrevistas, guiada por Claude.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="revisa ffmpeg, GPU y dependencias")
    s = sub.add_parser("ingest", help="analiza todos los videos: niveles, miniaturas, transcripción")
    s.add_argument("project")
    s = sub.add_parser("energy", help="mapa de energía del audio (para fijar cortes en silencios reales)")
    s.add_argument("project"); s.add_argument("src"); s.add_argument("a", type=float); s.add_argument("b", type=float)
    s.add_argument("--step", type=float, default=0.02)
    s = sub.add_parser("verify", help="escucha cortes: completo + solo inicio + solo final + bordes")
    s.add_argument("project"); s.add_argument("cuts", nargs="+", help="SRC A B [SRC A B ...]")
    s = sub.add_parser("spectrum", help="diagnóstico de voz saturada / embarrada")
    s.add_argument("project"); s.add_argument("src"); s.add_argument("a", type=float); s.add_argument("b", type=float)
    s = sub.add_parser("music-search", help="busca música CC0/CC BY en Openverse")
    s.add_argument("query"); s.add_argument("--license", default="cc0,by")
    s = sub.add_parser("music-get", help="descarga una pista"); s.add_argument("url"); s.add_argument("dest")
    s = sub.add_parser("music-profile", help="mapa de energía de una pista y drops candidatos"); s.add_argument("file")
    s = sub.add_parser("build", help="arma el reel desde reel.toml"); s.add_argument("project"); s.add_argument("--version", default="v1")
    s = sub.add_parser("check", help="QA del reel final"); s.add_argument("project"); s.add_argument("--version", default="v1")
    s.add_argument("--times", type=float, nargs="*")
    args = ap.parse_args()

    if args.cmd in ("ingest", "verify", "build", "check"):
        from .gpu import ensure_cuda_env
        ensure_cuda_env()

    if args.cmd == "doctor":
        from .doctor import doctor
        sys.exit(doctor())
    if args.cmd.startswith("music-"):
        from . import music
        if args.cmd == "music-search":
            return music.search(args.query, args.license)
        if args.cmd == "music-get":
            return music.download(args.url, args.dest)
        from .tools import Tools
        return music.profile(Tools(), args.file)

    from .project import Project
    p = Project(args.project)
    if args.cmd == "ingest":
        from .ingest import ingest
        ingest(p)
    elif args.cmd == "energy":
        from .verify import energy_map
        energy_map(p, args.src, args.a, args.b, args.step)
    elif args.cmd == "verify":
        from .verify import verify
        c = args.cuts
        if len(c) % 3:
            raise SystemExit("verify espera tríos: SRC A B")
        verify(p, [(c[i], float(c[i + 1]), float(c[i + 2])) for i in range(0, len(c), 3)])
    elif args.cmd == "spectrum":
        from .audio import spectrum_report
        print(spectrum_report(p.tools, p.media(args.src), args.a, args.b))
    elif args.cmd == "build":
        from .build import build
        build(p, args.version)
    elif args.cmd == "check":
        from .check import check
        check(p, args.version, args.times)


if __name__ == "__main__":
    main()
