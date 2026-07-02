"""
FASE 1 — Generador de datos de Homebanking.
Versión modificada: también procesa créditos nuevos no registrados en fagcuentacredito.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt
from sqlalchemy import create_engine, text
from app.core.cfg_config import settings


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()


def _catalogos(c):
    def pk(tabla, col, val):
        return c.execute(text(f"SELECT pk{tabla[1:]} FROM {tabla} WHERE {col}=:v LIMIT 1"),
                         {"v": val}).scalar()
    return {
        "tipo_cre": pk("dtipooperacion", "codtipooperacion", "CRE"),
        "tipo_deb": pk("dtipooperacion", "codtipooperacion", "DEB"),
        "con_dcap": pk("dconceptooperacion", "codconceptooperacion", "DCAP"),
        "con_pcap": pk("dconceptooperacion", "codconceptooperacion", "PCAP"),
        "con_pint": pk("dconceptooperacion", "codconceptooperacion", "PINT"),
        "medio_web": pk("dmediopago", "codmediopago", "WEB"),
        "medio_app": pk("dmediopago", "codmediopago", "APP"),
        "canal_web": pk("dcanaltransaccional", "codcanaltransaccional", "WEB"),
        "canal_app": pk("dcanaltransaccional", "codcanaltransaccional", "APP"),
        "cond_norm": pk("dcondicioncontable", "codcondicioncontable", "01"),
    }


def crear_usuarios(c):
    n = c.execute(text("""
        INSERT INTO usuarios_homebanking
            (pkcliente, username, password_hash, intentos_fallidos, bloqueado, activo, fecultactualizacion)
        SELECT DISTINCT cc.pkcliente,
               LOWER(TRIM(cl.codcliente)),
               :hash, 0, 'N', 'S', NOW()
        FROM dcuentacredito cc
        JOIN dcliente cl ON cl.pkcliente = cc.pkcliente
        WHERE NOT EXISTS (SELECT 1 FROM usuarios_homebanking u WHERE u.pkcliente = cc.pkcliente)
    """), {"hash": hash_password("demo1234")})
    return n.rowcount


def generar_operaciones(c, cat):
    desem = c.execute(text("""
        INSERT INTO foperaciones
            (codtipkar, codkardex, pkcuentacredito, pkconceptooperacion, pktipooperacion, pkmediopago,
             pkcanaltransaccional, pkmoneda, pkcondicioncontable, pkproducto,
             pkagenciaorigen, montooperacion, montopagoconcepto,
             codtipoegresoingreso, fechahoraoperacion, periododia, codusuope, fecultactualizacion)
        SELECT 'CR', 'DES-' || f.pkcuentacredito,
               f.pkcuentacredito, :con_dcap, :tipo_cre, :medio_web,
               :canal_web, f.pkmoneda, :cond_norm, f.pkproducto,
               f.pkagencia, f.montocapitaldesembolsado, f.montocapitaldesembolsado,
               'I', f.fechadesembolsocredito,
               CAST(TO_CHAR(f.fechadesembolsocredito,'YYYYMMDD') AS INTEGER), 'HB', NOW()
        FROM fagcuentacredito f
        WHERE f.montocapitaldesembolsado > 0
          AND EXISTS (SELECT 1 FROM dcuentacredito cc JOIN usuarios_homebanking u ON u.pkcliente=cc.pkcliente
                      WHERE cc.pkcuentacredito = f.pkcuentacredito)
          AND NOT EXISTS (SELECT 1 FROM foperaciones o
                          WHERE o.pkcuentacredito=f.pkcuentacredito AND o.pkconceptooperacion=:con_dcap)
    """), cat)

    pagos_cap = c.execute(text("""
        INSERT INTO foperaciones
            (codtipkar, codkardex, pkcuentacredito, nrocuotaplazo, pkconceptooperacion, pktipooperacion, pkmediopago,
             pkcanaltransaccional, pkmoneda, pkcondicioncontable, pkproducto,
             pkagenciaorigen, montooperacion, montopagoconcepto,
             codtipoegresoingreso, fechahoraoperacion, periododia, codusuope, fecultactualizacion)
        SELECT 'DB', 'PAG-' || p.pkcuentacredito || '-' || p.nrocuota,
               p.pkcuentacredito, p.nrocuota, :con_pcap, :tipo_deb, :medio_app,
               :canal_app, p.pkmoneda, :cond_norm, p.pkproducto,
               p.pkagencia, p.montocapitalpagado, p.montocapitalpagado,
               'E', COALESCE(p.fechapagocuota, p.fechavencimientopagocuota),
               CAST(TO_CHAR(COALESCE(p.fechapagocuota,p.fechavencimientopagocuota),'YYYYMMDD') AS INTEGER),
               'HB', NOW()
        FROM fplanpagomes p
        WHERE p.montocapitalpagado > 0
          AND EXISTS (SELECT 1 FROM usuarios_homebanking u WHERE u.pkcliente=p.pkcliente)
          AND NOT EXISTS (SELECT 1 FROM foperaciones o
                          WHERE o.pkcuentacredito=p.pkcuentacredito AND o.nrocuotaplazo=p.nrocuota
                            AND o.pkconceptooperacion=:con_pcap)
    """), cat)

    return desem.rowcount, pagos_cap.rowcount


def generar_operaciones_creditos_nuevos(c, cat):
    """Genera desembolso para créditos nuevos que NO están en fagcuentacredito."""
    pkmoneda = c.execute(text("SELECT pkmoneda FROM dmoneda LIMIT 1")).scalar()
    pkagencia = c.execute(text("SELECT pkagencia FROM dagencia LIMIT 1")).scalar()
    pkproducto = c.execute(text("SELECT pkproducto FROM dproducto LIMIT 1")).scalar()

    desem = c.execute(text("""
        INSERT INTO foperaciones
            (codtipkar, codkardex, pkcuentacredito, pkconceptooperacion, pktipooperacion, pkmediopago,
             pkcanaltransaccional, pkmoneda, pkcondicioncontable, pkproducto,
             pkagenciaorigen, montooperacion, montopagoconcepto,
             codtipoegresoingreso, fechahoraoperacion, periododia, codusuope, fecultactualizacion)
        SELECT 'CR', 'DES-' || cc.pkcuentacredito,
               cc.pkcuentacredito, :con_dcap, :tipo_cre, :medio_web,
               :canal_web, :pkmoneda, :cond_norm, :pkproducto,
               :pkagencia, s.montoaprobadocredito, s.montoaprobadocredito,
               'I', s.fechaaprobacioncredito,
               CAST(TO_CHAR(s.fechaaprobacioncredito,'YYYYMMDD') AS INTEGER), 'HB', NOW()
        FROM dcuentacredito cc
        JOIN dsolicitud s ON s.pkcliente = cc.pkcliente AND s.pksolicitud = cc.pkcuentacredito
        WHERE s.fechaaprobacioncredito IS NOT NULL
          AND s.montoaprobadocredito > 0
          AND NOT EXISTS (SELECT 1 FROM fagcuentacredito f WHERE f.pkcuentacredito = cc.pkcuentacredito)
          AND EXISTS (SELECT 1 FROM usuarios_homebanking u WHERE u.pkcliente = cc.pkcliente)
          AND NOT EXISTS (SELECT 1 FROM foperaciones o
                          WHERE o.pkcuentacredito = cc.pkcuentacredito AND o.pkconceptooperacion = :con_dcap)
    """), {**cat, "pkmoneda": pkmoneda, "pkagencia": pkagencia, "pkproducto": pkproducto})

    return desem.rowcount


def main():
    e = create_engine(settings.DATABASE_URL)
    with e.begin() as c:
        cat = _catalogos(c)
        faltan = [k for k, v in cat.items() if v is None]
        if faltan:
            print("[ERROR] catálogos no encontrados:", faltan)
            return
        nu = crear_usuarios(c)
        print(f"[OK] usuarios_homebanking nuevos: {nu}")
        nd, npg = generar_operaciones(c, cat)
        print(f"[OK] foperaciones desembolsos (históricos): {nd} | pagos de cuota: {npg}")
        nd_new = generar_operaciones_creditos_nuevos(c, cat)
        print(f"[OK] foperaciones desembolsos (créditos nuevos): {nd_new}")
        tot = c.execute(text("SELECT COUNT(*) FROM foperaciones")).scalar()
        tu = c.execute(text("SELECT COUNT(*) FROM usuarios_homebanking")).scalar()
        print(f"[TOTAL] usuarios={tu} | operaciones={tot}")
    print("Fase 1 completada.")


if __name__ == "__main__":
    main()