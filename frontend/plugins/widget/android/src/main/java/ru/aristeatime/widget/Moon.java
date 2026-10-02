package ru.aristeatime.widget;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;

/** Картинка фазы Луны в палитре «атлас» (наброски docs/widget_sketches). */
final class Moon {

    private static final double SYNODIC = 29.530588853;
    private static final long NEW_MOON_2000 = 947182440000L; // 06.01.2000 18:14 UTC

    private Moon() {}

    /**
     * Средний синодический месяц: ошибка до полусуток. Для картинки и подписи
     * в день, когда запас кончился, хватает; пока запас есть, элонгацию даёт
     * сервер (Swiss Ephemeris).
     */
    static double approxElongation(long ms) {
        double days = (ms - NEW_MOON_2000) / 86400000.0;
        double age = ((days % SYNODIC) + SYNODIC) % SYNODIC;
        return age / SYNODIC * 360;
    }

    /**
     * Освещённая часть — полукруг по освещённому краю плюс полуэллипс
     * терминатора. Растущая освещена справа (северное полушарие).
     * Углы Path: 0° — справа, по часовой; −90° — верх.
     */
    static Bitmap draw(int size, double elong) {
        Bitmap b = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas cv = new Canvas(b);
        float stroke = Math.max(1f, size / 48f);
        float c = size / 2f;
        float r = c - stroke;

        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(0xFF1A2747);
        cv.drawCircle(c, c, r, p);

        double k = (1 - Math.cos(Math.toRadians(elong))) / 2; // доля освещённого диска
        boolean waxing = elong < 180;
        float rx = (float) Math.abs(1 - 2 * k) * r;
        Path lit = new Path();
        lit.moveTo(c, c - r);
        lit.arcTo(new RectF(c - r, c - r, c + r, c + r), -90, waxing ? 180 : -180);
        if (rx < 0.5f) {
            lit.lineTo(c, c - r); // четверть: терминатор — прямая
        } else {
            // Серп — терминатор выгнут к освещённому краю, горб — от него.
            lit.arcTo(new RectF(c - rx, c - r, c + rx, c + r), 90, (waxing == (k < 0.5)) ? -180 : 180);
        }
        lit.close();
        p.setColor(0xFFD9B56A);
        cv.drawPath(lit, p);

        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(stroke);
        p.setColor(0x73D9B56A); // золото с прозрачностью .45
        cv.drawCircle(c, c, r, p);
        return b;
    }
}
