"""E28 — CAPA DE PRODUCTO: la PROPIEDAD.

Hasta E27.3 el objeto central de Escalímetro era el CASE: una planta que el motor sabe interpretar.
Eso sigue siendo cierto y no se toca. Lo que E28 agrega es un objeto POR ENCIMA, que es el que
entiende un cliente:

    DOMINIO DE CLIENTE          DOMINIO TÉCNICO DEL MOTOR
    PROPERTY  ────────────────► CASE  ──► floorplate ──► layouts A/B/C

La relación es de UN SOLO SENTIDO: `Property.floorplan_case_id` apunta a un CASE existente. El motor
no sabe que existen propiedades y no debe saberlo. Nada de `webapp/domain/` se importa desde
`src/escalimetro/`, y ninguna función de aquí escribe en los artefactos del motor.

Por qué no se migró CASE a PROPERTY: un CASE puede existir sin propiedad (los tres que ya están en
el volumen lo hacen), y una propiedad puede existir sin caso (recién creada). Fusionarlos habría
sido una migración destructiva a cambio de nada.
"""
