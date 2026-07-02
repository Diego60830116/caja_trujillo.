"""
Repositorio de evaluación y desembolso de solicitudes — MPR-003-CRE (actividades 11, 16, 45-48).
"""
from datetime import datetime
import calendar
from datetime import date as date_
from sqlalchemy.orm import Session
from sqlalchemy import text

PERIODO = 202512


def registrar_ingreso(db: Session, pkcliente: int, *, tipo: str, monto: float,
                      nombre_empresa: str = None) -> dict:
    db.execute(text("""
        INSERT INTO fclientefuenteingreso
            (pkcliente, periodomes, tipofuenteingreso, montofuenteingreso,
             codrelacion, nombreempresa, fecultactualizacion)
        VALUES (:pk, :per, :tipo, :monto, 'T', :emp, NOW())
        ON CONFLICT (pkcliente, periodomes) DO UPDATE
            SET tipofuenteingreso = EXCLUDED.tipofuenteingreso,
                montofuenteingreso = EXCLUDED.montofuenteingreso,
                nombreempresa = EXCLUDED.nombreempresa,
                fecultactualizacion = NOW()
    """), {"pk": pkcliente, "per": PERIODO, "tipo": tipo[:2],
           "monto": monto, "emp": nombre_empresa})
    db.commit()
    return {"pkcliente": pkcliente, "tipo": tipo, "monto": monto}


def registrar_evaluacion(db: Session, codsolicitud: str, *, es_microempresa: bool,
                         ingreso: float, gasto_familiar: float,
                         monto_solicitud: float = 0.0,
                         fortaleza: str = "", debilidad: str = "") -> dict:
    ya = db.execute(text("SELECT pkevaluacion FROM devaluacion WHERE codsolicitud=:c"),
                    {"c": codsolicitud}).scalar()
    if ya:
        return {"codsolicitud": codsolicitud, "pkevaluacion": ya, "creada": False}

    excedente = round(ingreso - gasto_familiar, 2)
    row = db.execute(text("""
        INSERT INTO devaluacion
            (nroevaluacion, valorexcedentecredito, tipoevaluacion, codsolicitud, fecultactualizacion)
        VALUES ('EV-' || :c, :exc, :tipo, :c, NOW())
        RETURNING pkevaluacion
    """), {"c": codsolicitud, "exc": excedente, "tipo": "ME" if es_microempresa else "CO"}).fetchone()
    pkeval = row.pkevaluacion

    if es_microempresa:
        db.execute(text("""
            INSERT INTO fevalmicroactivo
                (pkevaluacion, nroreg, montoactivodisponible, montoactivoinventario,
                 montoactivofijo, montogastofamiliar, fecultactualizacion)
            VALUES (:pk, 1, :disp, :inv, :fijo, :gf, NOW())
        """), {"pk": pkeval, "disp": round(monto_solicitud*0.20, 2),
               "inv": round(monto_solicitud*0.50, 2), "fijo": round(monto_solicitud*0.80, 2),
               "gf": gasto_familiar})
    else:
        db.execute(text("""
            INSERT INTO fevalconsumo
                (pkevaluacion, monto, montogastofamiliar, codtipoingreso,
                 fortalezaevaluacion, debilidadevaluacion, fecultactualizacion)
            VALUES (:pk, :monto, :gf, 'D', :fz, :db, NOW())
        """), {"pk": pkeval, "monto": ingreso, "gf": gasto_familiar,
               "fz": fortaleza or "Ingreso estable", "db": debilidad or "Sin garantía real"})
    db.commit()
    return {"codsolicitud": codsolicitud, "pkevaluacion": pkeval, "excedente": excedente, "creada": True}


def desembolsar(db: Session, sol) -> dict:
    monto = float(sol.montoaprobadocredito or sol.montosolicitudcredito or 0)
    plazo = int(sol.plazosolicitudcredito or sol.nrocuotasolicitud or 12)
    nrodias = plazo * 30

    # 1. Crear cuenta de crédito
    cc = db.execute(text("""
        INSERT INTO dcuentacredito (pkcuentacredito, codcuentacredito, pkcliente, nrocronograma, fecultactualizacion)
        VALUES (nextval('dcuentacredito_pkcuentacredito_seq'),
                'CRD' || LPAD(currval('dcuentacredito_pkcuentacredito_seq')::text, 7, '0'),
                :pkcli, 1, NOW())
        RETURNING pkcuentacredito, codcuentacredito
    """), {"pkcli": sol.pkcliente}).fetchone()

    # 2. Obtener catálogos
    cat = db.execute(text("""
        SELECT (SELECT pkconceptooperacion FROM dconceptooperacion WHERE codconceptooperacion='DCAP') con,
               (SELECT pktipooperacion FROM dtipooperacion WHERE codtipooperacion='CRE') tipo,
               (SELECT pkmediopago FROM dmediopago WHERE codmediopago='WEB') medio,
               (SELECT pkcanaltransaccional FROM dcanaltransaccional WHERE codcanaltransaccional='WEB') canal,
               (SELECT pkcondicioncontable FROM dcondicioncontable WHERE codcondicioncontable='01') cond,
               (SELECT pkmoneda FROM dmoneda ORDER BY pkmoneda LIMIT 1) mon,
               (SELECT MIN(pkproducto) FROM dproducto) prod,
               (SELECT MIN(pkagencia) FROM dagencia) ag,
               (SELECT MIN(pkestadocredito) FROM destadocredito) est,
               (SELECT MIN(pkactividadeconomica) FROM dactividadeconomica) act,
               1 AS cal
    """)).fetchone()

    hoy = datetime.utcnow()
    pd_val = int(hoy.strftime("%Y%m%d"))
    periodomes = int(hoy.strftime("%Y%m"))

    # Obtener pkasesor de referencia
    pkasesor = db.execute(text("""
        SELECT pkasesor FROM fplanpagomes WHERE pkagencia = :ag AND pkasesor IS NOT NULL LIMIT 1
    """), {"ag": cat.ag}).scalar() or 1

    # 3. Registrar movimiento de desembolso
    db.execute(text("""
        INSERT INTO foperaciones
            (codtipkar, codkardex, pkcuentacredito, pkconceptooperacion, pktipooperacion,
             pkmediopago, pkcanaltransaccional, pkmoneda, pkcondicioncontable, pkproducto,
             pkagenciaorigen, montooperacion, montopagoconcepto, codtipoegresoingreso,
             fechahoraoperacion, periododia, codusuope, fecultactualizacion)
        VALUES ('CR', 'DESEMB-' || :pkcc, :pkcc, :con, :tipo, :medio, :canal, :mon, :cond, :prod,
                :ag, :monto, :monto, 'I', :fh, :pd, 'CORE', NOW())
    """), {"pkcc": cc.pkcuentacredito, "con": cat.con, "tipo": cat.tipo, "medio": cat.medio,
           "canal": cat.canal, "mon": cat.mon, "cond": cat.cond, "prod": cat.prod,
           "ag": cat.ag, "monto": monto, "fh": hoy, "pd": pd_val})

    # 4. Insertar en fagcuentacredito (106 columnas exactas)
    db.execute(text("""
        INSERT INTO fagcuentacredito (
            periodomes,                    -- 1
            pkcuentacredito,               -- 2
            pksolicitud,                   -- 3
            pkestadocredito,               -- 4
            nrocuotas,                     -- 5
            nrodias,                       -- 6
            nrodiasgracias,                -- 7
            diafechafija,                  -- 8
            codtipocuota,                  -- 9
            codtipoperiodo,                -- 10
            flaglibreamortizacion,         -- 11
            montoaprobadocredito,          -- 12
            montocapitaldesembolsado,      -- 13
            montocapitalpagado,            -- 14
            montointeresprogramado,        -- 15
            montointeresalafecha,          -- 16
            montointerespagado,            -- 17
            montomoraprogramada,           -- 18
            montomorapagada,               -- 19
            montogastoprogramado,          -- 20
            montogastopagado,              -- 21
            pkproducto,                    -- 22
            pkrecurso,                     -- 23
            pksubrecurso,                  -- 24
            pkmoneda,                      -- 25
            pkmodalidad,                   -- 26
            codplazo,                      -- 27
            codlineacredito,               -- 28
            nrotasacompensatoria,          -- 29
            tasainterescompensatoria,      -- 30
            nrotasamoratoria,              -- 31
            tasainteresmoratoria,          -- 32
            diasatrasocredito,             -- 33
            fechaculminacioncredito,       -- 34
            fechageneracioncredito,        -- 35
            fechadesembolsocredito,        -- 36
            tipocambiodesembolso,          -- 37
            pkgrupocredito,                -- 38
            flagrefinanciado,              -- 39
            flagreestructurado,            -- 40
            flagreprogramado,              -- 41
            flagjudicial,                  -- 42
            flagcastigado,                 -- 43
            pkactividadeconomica,          -- 44
            montosaldonormal,              -- 45
            montosaldovencido,             -- 46
            flagnuevorecurrente,           -- 47
            montocostoefectivo,            -- 48
            pktipotasacompensatoria,       -- 49
            pktipotasamoratoria,           -- 50
            pkcliente,                     -- 51
            nrocronograma,                 -- 52
            pkcondicioncontable,           -- 53
            flagclientenuevobancoandino,   -- 54
            flagclientenuevo,              -- 55
            flagclientecartera,            -- 56
            pkcalificacioncrediticiainterna,  -- 57
            pkcalificacioncrediticiaexterna,  -- 58
            fechaingresojudicial,          -- 59
            montocapitalinicio,            -- 60
            montointeresinicio,            -- 61
            montomorainicio,               -- 62
            montogastoinicio,              -- 63
            nrodiasatrasoinicio,           -- 64
            montosaldocapital,             -- 65
            montosaldointeres,             -- 66
            montosaldomoratorio,           -- 67
            montosaldogasto,               -- 68
            car_vig_capital,               -- 69
            car_vig_int_compensatorio,     -- 70
            car_vig_int_moratorio,         -- 71
            car_vig_gastos,                -- 72
            car_ven_capital,               -- 73
            car_ven_int_compensatorio,     -- 74
            car_ven_int_moratorio,         -- 75
            car_ven_gastos,                -- 76
            car_ref_capital,               -- 77
            car_ref_int_compensatorio,     -- 78
            car_ref_int_moratorio,         -- 79
            car_ref_gastos,                -- 80
            car_rep_capital,               -- 81
            car_rep_int_compensatorio,     -- 82
            car_rep_int_moratorio,         -- 83
            car_rep_gastos,                -- 84
            car_jud_capital,               -- 85
            car_jud_int_compensatorio,     -- 86
            car_jud_int_moratorio,         -- 87
            car_jud_gastos,                -- 88
            car_cas_capital,               -- 89
            car_cas_int_compensatorio,     -- 90
            car_cas_int_moratorio,         -- 91
            car_cas_gastos,                -- 92
            car_con_capital,               -- 93
            car_con_int_compensatorio,     -- 94
            car_con_int_moratorio,         -- 95
            car_con_gastos,                -- 96
            saldodiferido,                 -- 97
            saldodevengado,                -- 98
            saldoprovisiones,              -- 99
            montosaldocliente,             -- 100
            pkagencia,                     -- 101
            pkjeferegional,                -- 102
            pkadministrador,               -- 103
            pkasesor,                      -- 104
            pkasesornivel,                 -- 105
            fecultactualizacion            -- 106
        ) VALUES (
            :periodomes,                                                                    -- 1
            :pkcc,                                                                          -- 2
            :pksol,                                                                         -- 3
            :est,                                                                           -- 4
            :plazo,                                                                         -- 5
            :nrodias,                                                                       -- 6
            0,                                                                              -- 7
            (SELECT diafechafija FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),        -- 8
            (SELECT codtipocuota FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),        -- 9
            (SELECT codtipoperiodo FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),      -- 10
            (SELECT flaglibreamortizacion FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 11
            :monto,                                                                         -- 12
            :monto,                                                                         -- 13
            0,                                                                              -- 14
            0,                                                                              -- 15
            0,                                                                              -- 16
            0,                                                                              -- 17
            0,                                                                              -- 18
            0,                                                                              -- 19
            0,                                                                              -- 20
            0,                                                                              -- 21
            (SELECT pkproducto FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),          -- 22
            (SELECT pkrecurso FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),           -- 23
            (SELECT pksubrecurso FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),        -- 24
            (SELECT pkmoneda FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),            -- 25
            (SELECT pkmodalidad FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),         -- 26
            (SELECT codplazo FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),            -- 27
            (SELECT codlineacredito FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),     -- 28
            (SELECT nrotasacompensatoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 29
            (SELECT tasainterescompensatoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 30
            (SELECT nrotasamoratoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),    -- 31
            (SELECT tasainteresmoratoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 32
            0,                                                                              -- 33
            (NOW() + INTERVAL '1 year')::date,                                             -- 34
            NOW()::date,                                                                    -- 35
            NOW()::date,                                                                    -- 36
            (SELECT tipocambiodesembolso FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 37
            (SELECT pkgrupocredito FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),      -- 38
            'N',                                                                            -- 39
            'N',                                                                            -- 40
            'N',                                                                            -- 41
            'N',                                                                            -- 42
            'N',                                                                            -- 43
            :act,                                                                           -- 44
            :monto,                                                                         -- 45
            0,                                                                              -- 46
            'N',                                                                            -- 47
            (SELECT montocostoefectivo FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1),  -- 48
            (SELECT pktipotasacompensatoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 49
            (SELECT pktipotasamoratoria FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 50
            :pkcli,                                                                         -- 51
            1,                                                                              -- 52
            (SELECT pkcondicioncontable FROM fagcuentacredito WHERE pkagencia=:ag LIMIT 1), -- 53
            'N',                                                                            -- 54
            'N',                                                                            -- 55
            'S',                                                                            -- 56
            :cal,                                                                           -- 57
            :cal,                                                                           -- 58
            NULL,                                                                           -- 59
            :monto,                                                                         -- 60
            0,                                                                              -- 61
            0,                                                                              -- 62
            0,                                                                              -- 63
            0,                                                                              -- 64
            :monto,                                                                         -- 65
            0,                                                                              -- 66
            0,                                                                              -- 67
            0,                                                                              -- 68
            :monto,                                                                         -- 69
            0,                                                                              -- 70
            0,                                                                              -- 71
            0,                                                                              -- 72
            0,                                                                              -- 73
            0,                                                                              -- 74
            0,                                                                              -- 75
            0,                                                                              -- 76
            0,                                                                              -- 77
            0,                                                                              -- 78
            0,                                                                              -- 79
            0,                                                                              -- 80
            0,                                                                              -- 81
            0,                                                                              -- 82
            0,                                                                              -- 83
            0,                                                                              -- 84
            0,                                                                              -- 85
            0,                                                                              -- 86
            0,                                                                              -- 87
            0,                                                                              -- 88
            0,                                                                              -- 89
            0,                                                                              -- 90
            0,                                                                              -- 91
            0,                                                                              -- 92
            0,                                                                              -- 93
            0,                                                                              -- 94
            0,                                                                              -- 95
            0,                                                                              -- 96
            0,                                                                              -- 97
            0,                                                                              -- 98
            0,                                                                              -- 99
            :monto,                                                                         -- 100
            :ag,                                                                            -- 101
            NULL,                                                                           -- 102
            NULL,                                                                           -- 103
            :pkasesor,                                                                      -- 104
            NULL,                                                                           -- 105
            NOW()                                                                           -- 106
        )
    """), {
        "periodomes": periodomes,
        "pkcc": cc.pkcuentacredito,
        "pksol": sol.pksolicitud,
        "est": cat.est,
        "plazo": plazo,
        "nrodias": nrodias,
        "monto": monto,
        "act": cat.act,
        "cal": cat.cal,
        "pkcli": sol.pkcliente,
        "ag": cat.ag,
        "pkasesor": pkasesor,
    })

    # 5. Generar cronograma de cuotas en fplanpagomes
    cuota_base = round(monto / plazo, 2)
    cuota_ultima = round(monto - cuota_base * (plazo - 1), 2)
    codplanpago = "PLAN" + str(cc.pkcuentacredito).zfill(7)

    for n in range(1, plazo + 1):
        monto_cuota = cuota_base if n < plazo else cuota_ultima
        monto_saldo = round(monto - cuota_base * (n - 1), 2) if n < plazo else 0.0
        mes = hoy.month + n
        anio = hoy.year + (mes - 1) // 12
        mes = ((mes - 1) % 12) + 1
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        dia = min(hoy.day, ultimo_dia)
        fecha_venc = date_(anio, mes, dia)
        periodo_cuota = int(fecha_venc.strftime("%Y%m"))

        db.execute(text("""
            INSERT INTO fplanpagomes (
                periodomes, pkcuentacredito, codplanpago, nrocuota,
                pksolicitud, pkestadocredito, pkproducto, pkmoneda,
                pkmodalidad, pkgrupocredito, pkactividadeconomica,
                pktipotasacompensatoria, pktipotasamoratoria,
                pkcliente, pkcondicioncontable, pkcalificacioncrediticiainterna,
                pkagencia, pkjeferegional, pkadministrador, pkasesor, pkasesornivel,
                pkestadodesembolso, pkmodalidadpago,
                codestadocuota, codestadoplan,
                fechavencimientopagocuota, fechapagocuota,
                montocuota, montosaldo, montomora,
                montocuotavencida, montocuotaatrasada,
                montointeresprogramado, montointerespagado, montointeresalafecha,
                montomoraprogramado, montomorapagada,
                montogasto, montogastoprogramado, montogastopagado,
                montosaldocapital, montocapitalpagado, montocapitalprogramado,
                montocapitaldesembolsado,
                diasatrasocuota, diasvencidocuota,
                interesdevengadocuota, montopagoanticipado, montopagoparcial,
                fecultactualizacion
            ) VALUES (
                :periodomes, :pkcc, :codplan, :nrocuota,
                :pksol, :est, :prod, :mon,
                NULL, NULL, :act,
                NULL, NULL,
                :pkcli, :cond, NULL,
                :ag, NULL, NULL, :asesor, NULL,
                NULL, NULL,
                '01', NULL,
                :fecha_venc, NULL,
                :montocuota, :montosaldo, 0,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                :montosaldo, 0, :montocuota,
                :monto_total,
                0, 0, 0, 0, 0,
                NOW()
            )
        """), {
            "periodomes": periodo_cuota,
            "pkcc": cc.pkcuentacredito,
            "codplan": codplanpago,
            "nrocuota": n,
            "pksol": sol.pksolicitud,
            "est": cat.est,
            "prod": cat.prod,
            "mon": cat.mon,
            "act": cat.act,
            "pkcli": sol.pkcliente,
            "cond": cat.cond,
            "ag": cat.ag,
            "asesor": pkasesor,
            "fecha_venc": fecha_venc,
            "montocuota": monto_cuota,
            "montosaldo": monto_saldo,
            "monto_total": monto,
        })

    # 6. Crear cuenta de ahorros si el cliente no tiene una, y abonar el monto
    ca = db.execute(text("""
        SELECT pkcuentaahorro FROM dcuentaahorro WHERE pkcliente = :pkcli LIMIT 1
    """), {"pkcli": sol.pkcliente}).fetchone()

    if not ca:
        ca = db.execute(text("""
            INSERT INTO dcuentaahorro (
                codcuentaahorro, pkcliente, fecultactualizacion
            ) VALUES (
                'AHO' || LPAD((SELECT COALESCE(MAX(pkcuentaahorro), 0) + 1 FROM dcuentaahorro)::text, 7, '0'),
                :pkcli, NOW()
            ) RETURNING pkcuentaahorro
        """), {"pkcli": sol.pkcliente}).fetchone()

        ref = db.execute(text("""
            SELECT * FROM fcuentaahorro LIMIT 1
        """)).fetchone()

        db.execute(text("""
            INSERT INTO fcuentaahorro (
                periododia, pkcuentaahorro, pkproductoahorro, pkmoneda,
                pktipocuentaahorro, pktipotasaahorro, pkcliente,
                pkauxiliar, pkoperador, pkadministrador, pkjeferegional,
                pkagencia, pkestadocuenta, tipocambio,
                montosaldocapitaltotal, montosaldointerestotal, montosaldopromediototal,
                fechaaperturacuenta, montodepositoapertura,
                tasainterescuenta, tasaefectivaanual, nrotitulares, nrofirmas,
                flagexoneracionimpuesto, flagexoneracioncomision, flagcuentapromocion,
                nrooperacioneslibres, fechaultimaconsulta, flag_ac,
                montosaldodisponible_ac, montosaldominimo_ac, montosaldocontable_ac,
                montointeresacuantcap_ac, nrooperaciones_ac,
                flag_pf, flag_cts, flag_ap, fecultactualizacion
            ) VALUES (
                :pd, :pkca, :prod, :mon,
                :tipo, :tasa, :pkcli,
                :aux, :oper, :adm, NULL,
                :ag, :est, 1.0,
                0, 0, 0,
                NOW()::date, 0,
                0, 0, 1, 1,
                'N', 'N', 'N',
                0, NOW()::date, 'S',
                0, 0, 0, 0, 0,
                'N', 'N', 'N', NOW()
            )
        """), {
            "pd": int(hoy.strftime("%Y%m%d")),
            "pkca": ca.pkcuentaahorro,
            "prod": ref.pkproductoahorro,
            "mon": ref.pkmoneda,
            "tipo": ref.pktipocuentaahorro,
            "tasa": ref.pktipotasaahorro,
            "pkcli": sol.pkcliente,
            "aux": ref.pkauxiliar,
            "oper": ref.pkoperador,
            "adm": ref.pkadministrador,
            "ag": ref.pkagencia,
            "est": ref.pkestadocuenta,
        })

    pkcuentaahorro = ca.pkcuentaahorro

    # Actualizar saldo en fcuentaahorro
    db.execute(text("""
        UPDATE fcuentaahorro
        SET montosaldocapitaltotal   = montosaldocapitaltotal + :monto,
            montosaldodisponible_ac  = montosaldodisponible_ac + :monto,
            montosaldocontable_ac    = montosaldocontable_ac + :monto,
            fecultactualizacion      = NOW()
        WHERE pkcuentaahorro = :pkca
          AND periododia = (
              SELECT MAX(periododia) FROM fcuentaahorro WHERE pkcuentaahorro = :pkca
          )
    """), {"pkca": pkcuentaahorro, "monto": monto})

    db.commit()
    return {"codcuentacredito": cc.codcuentacredito, "monto_desembolsado": monto,
            "fecha": hoy.date().isoformat()}