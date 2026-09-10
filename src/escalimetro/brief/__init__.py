"""E24 — Capa de brief: QUÉ PIDE EL CLIENTE, separado de CÓMO ESCALÍMETRO LO DISEÑA."""
from .brief_v1 import (BriefV1, BriefError, load_brief, compile_program,
                       brief_from_legacy_program, CONTRACT_VERSION)
from .design_policy_v1 import DesignPolicyV1, DEFAULT_POLICY
from .apportion import apportion
from .display import program_rows, program_kpis, program_band_items, total_rooms, room_counts

__all__ = ["BriefV1", "BriefError", "load_brief", "compile_program",
           "brief_from_legacy_program", "CONTRACT_VERSION",
           "DesignPolicyV1", "DEFAULT_POLICY", "apportion",
           "program_rows", "program_kpis", "program_band_items", "total_rooms", "room_counts"]
