from backend.database import get_db
from backend.models import NatalChart
db = next(get_db())
chart = db.query(NatalChart).first()
print('tz:', chart.timezone)
print('system:', getattr(chart, 'house_system', 'unknown'))
for h in (chart.houses or []):
    print(f'h{h["number"]}: {h["degree"]:.4f} {h["sign"]}')
