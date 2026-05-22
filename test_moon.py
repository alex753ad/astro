import swisseph as swe, os
swe.set_ephe_path(os.getenv('EPHE_PATH', 'data/ephe'))
jd0 = swe.julday(2026, 4, 29, 0)
for target in [0, 180]:
    jd = jd0
    for _ in range(3):
        exact = swe.mooncross_ut(target, jd, swe.FLG_SWIEPH)
        y, mo, d, h = swe.revjul(exact)
        print(f"target={target} -> {int(y)}-{int(mo):02d}-{int(d):02d} {h:.4f}h UTC")
        jd = exact + 27
