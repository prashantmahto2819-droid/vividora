"""60 named 3D character profiles — professions, families, regional/festive outfits. Each profile is a
spec for web/dist/assets/chars3d.js buildCharacter(): outfit + hair + skin + build + props; the look is
procedural, so two profiles with the same outfit still differ in body, hair, colours and props."""

from __future__ import annotations

# (id, name, category, spec)
_P: list[tuple[str, str, str, dict]] = []


def _add(pid, name, cat, **spec):
    _P.append((pid, name, cat, spec))


# --- medical --------------------------------------------------------------------------------------
_add("doctor_m", "Dr. Arjun (physician)", "medical", outfit="doctor", hair="short", skin="wheat", gender="m", props=["glasses"], build=1.0)
_add("doctor_f", "Dr. Meera (gynecologist)", "medical", outfit="doctor", hair="bun", skin="tan", gender="f", build=0.9, colors={"torso": 0xfbcfe8})
_add("cardio", "Dr. Khan (cardiologist)", "medical", outfit="doctor", hair="short", skin="fair", gender="m", beard=True, age="old", build=1.1)
_add("pedia", "Dr. Priya (pediatrician)", "medical", outfit="doctor", hair="ponytail", skin="wheat", gender="f", colors={"torso": 0xfde68a}, build=0.85)
_add("dentist", "Dr. Rohan (dentist)", "medical", outfit="labcoat", hair="short", skin="brown", gender="m", props=["glasses"], colors={"legs": 0x1e3a8a})
_add("surgeon", "Dr. Sunita (surgeon)", "medical", outfit="nurse", hair="bun", skin="tan", gender="f", colors={"torso": 0x14b8a6, "sleeves": 0x14b8a6, "legs": 0x14b8a6})
_add("nurse", "Nurse Anjali", "medical", outfit="nurse", hair="bun", skin="wheat", gender="f", build=0.9)
_add("labtech", "Lab technician Vikas", "medical", outfit="labcoat", hair="short", skin="dark", gender="m", props=["glasses"], build=0.95)
# --- shops & business -----------------------------------------------------------------------------
_add("grocer", "Sharma ji (grocery)", "retail", outfit="apron", hair="short", skin="wheat", gender="m", age="old", build=1.25, colors={"apron": 0x16a34a})
_add("grocer_f", "Geeta (kirana store)", "retail", outfit="apron", hair="bun", skin="tan", gender="f", build=1.1, colors={"apron": 0xf59e0b})
_add("electronics", "Sameer (electronics shop)", "retail", outfit="shirt", hair="short", skin="wheat", gender="m", props=["phone"], build=1.0)
_add("auto", "Deepak (car dealer)", "retail", outfit="suit", hair="short", skin="fair", gender="m", props=["phone"], build=1.05)
_add("cloth", "Nisha (clothing store)", "retail", outfit="saree", hair="long", skin="wheat", gender="f", build=0.9, colors={"torso": 0x7c3aed, "drape": 0xfacc15})
_add("jewel", "Mehta ji (jewellery)", "retail", outfit="kurta", hair="short", skin="fair", gender="m", age="old", build=1.2, props=["glasses"])
_add("chemist", "Rahul (medical store)", "retail", outfit="apron", hair="short", skin="brown", gender="m", colors={"apron": 0xffffff})
_add("sweet", "Chef Ramesh (sweets)", "retail", outfit="chef", hair="bald", skin="wheat", gender="m", build=1.3)
_add("ceo", "Ananya (founder)", "business", outfit="suit", hair="bun", skin="tan", gender="f", build=0.9, colors={"torso": 0x374151, "tie": 0x9333ea})
_add("manager", "Manoj (manager)", "business", outfit="shirt", hair="short", skin="wheat", gender="m", props=["laptop"], build=1.1, colors={"torso": 0xbfdbfe})
_add("exec", "Mr. Iyer (executive)", "business", outfit="suit", hair="short", skin="brown", gender="m", age="old", props=["glasses"], build=1.0)
_add("employee", "Kavya (office)", "business", outfit="shirt", hair="ponytail", skin="fair", gender="f", props=["laptop"], build=0.85, colors={"torso": 0xfce7f3})
_add("startup", "Aditya (startup)", "business", outfit="tshirt", hair="curly", skin="wheat", gender="m", props=["laptop"], build=0.95, colors={"torso": 0x111827})
_add("banker", "Sunil (bank)", "business", outfit="suit", hair="short", skin="tan", gender="m", build=1.05, colors={"torso": 0x1e3a8a, "tie": 0xdc2626})
# --- education --------------------------------------------------------------------------------------
_add("teacher_f", "Sarita ma'am (teacher)", "education", outfit="saree", hair="bun", skin="wheat", gender="f", props=["pointer"], build=0.95, colors={"torso": 0x0e7490, "drape": 0xfde68a})
_add("teacher_m", "Verma sir (teacher)", "education", outfit="shirt", hair="short", skin="brown", gender="m", props=["glasses", "book"], age="old", build=1.05)
_add("student_b", "Aarav (student)", "education", outfit="school", hair="short", skin="wheat", gender="m", age="child", build=0.9)
_add("student_g", "Riya (student)", "education", outfit="school", hair="ponytail", skin="tan", gender="f", age="child", build=0.85, colors={"legs": 0x7f1d1d})
_add("college", "Neha (college)", "education", outfit="tshirt", hair="long", skin="fair", gender="f", age="teen", props=["book"], build=0.85, colors={"torso": 0xf472b6})
_add("engineer", "Engineer Karan", "education", outfit="helmet", hair="short", skin="wheat", gender="m", build=1.05)
_add("architect", "Architect Pooja", "education", outfit="shirt", hair="bun", skin="tan", gender="f", props=["glasses"], build=0.9, colors={"torso": 0x111827})
_add("coach", "Coaching sir Alok", "education", outfit="kurta", hair="short", skin="wheat", gender="m", props=["pointer"], build=1.1, colors={"torso": 0x1d4ed8, "legs": 0xffffff})
# --- fitness, beauty, services -------------------------------------------------------------------------
_add("trainer_m", "Gym trainer Rocky", "fitness", outfit="gym", hair="short", skin="tan", gender="m", build=1.35)
_add("trainer_f", "Yoga coach Divya", "fitness", outfit="gym", hair="ponytail", skin="wheat", gender="f", build=0.85, colors={"torso": 0xec4899, "legs": 0x111827})
_add("salon_f", "Salon artist Simran", "fitness", outfit="salon", hair="long", skin="fair", gender="f", build=0.9, colors={"apron": 0x111111})
_add("spa", "Spa therapist Maya", "fitness", outfit="nurse", hair="bun", skin="tan", gender="f", build=0.9, colors={"torso": 0xa7f3d0, "sleeves": 0xa7f3d0, "legs": 0xa7f3d0})
_add("barber", "Barber Imran", "fitness", outfit="salon", hair="short", skin="brown", gender="m", beard=True, build=1.0)
_add("driver", "Driver Santosh", "service", outfit="driver", hair="short", skin="brown", gender="m", build=1.1)
_add("mechanic", "Mechanic Raju", "service", outfit="mechanic", hair="short", skin="dark", gender="m", build=1.15)
_add("delivery", "Delivery partner Vijay", "service", outfit="delivery", hair="short", skin="tan", gender="m", build=1.0)
_add("police", "Inspector Rathore", "service", outfit="police", hair="short", skin="wheat", gender="m", beard=True, build=1.15)
_add("security", "Guard Bahadur", "service", outfit="police", hair="short", skin="brown", gender="m", age="old", build=1.1, colors={"torso": 0x1f2937, "sleeves": 0x1f2937, "legs": 0x1f2937})
_add("chef", "Chef Antony", "service", outfit="chef", hair="short", skin="fair", gender="m", build=1.2)
_add("farmer", "Kisan Ramlal", "service", outfit="kurta", hair="short", skin="dark", gender="m", age="old", props=["hat"], build=1.0, colors={"torso": 0xf5f5f4})
_add("tailor", "Tailor Master Salim", "service", outfit="apron", hair="short", skin="brown", gender="m", props=["glasses"], age="old", build=0.95)
_add("electrician", "Electrician Mukesh", "service", outfit="mechanic", hair="curly", skin="tan", gender="m", props=["bag"], build=1.0, colors={"torso": 0xf59e0b, "sleeves": 0xf59e0b, "legs": 0xf59e0b})
# --- family -----------------------------------------------------------------------------------------
_add("dad", "Papa (40s)", "family", outfit="shirt", hair="short", skin="wheat", gender="m", build=1.15, colors={"torso": 0xc7d2fe})
_add("mom", "Mummy (40s)", "family", outfit="saree", hair="bun", skin="wheat", gender="f", build=1.0, colors={"torso": 0x16a34a, "drape": 0xfacc15})
_add("grandpa", "Dadaji", "family", outfit="kurta", hair="bald", skin="tan", gender="m", age="old", props=["glasses"], build=1.0)
_add("grandma", "Dadiji", "family", outfit="saree", hair="bun", skin="tan", gender="f", age="old", build=1.05, colors={"torso": 0xf5f5f4, "drape": 0xdc2626}, hairColor=0xd1d5db)
_add("boy", "Chotu (8)", "family", outfit="tshirt", hair="short", skin="wheat", gender="m", age="child", build=0.9, colors={"torso": 0xf59e0b})
_add("girl", "Gudiya (7)", "family", outfit="tshirt", hair="ponytail", skin="fair", gender="f", age="child", build=0.85, colors={"torso": 0xec4899, "legs": 0x7c3aed})
_add("teen_b", "Rohit (16)", "family", outfit="tshirt", hair="curly", skin="tan", gender="m", age="teen", props=["phone"], build=0.9, colors={"torso": 0x111827})
_add("teen_g", "Isha (15)", "family", outfit="tshirt", hair="long", skin="wheat", gender="f", age="teen", props=["phone"], build=0.8, colors={"torso": 0x60a5fa, "legs": 0x1e3a8a})
_add("uncle", "Chacha ji", "family", outfit="kurta", hair="short", skin="brown", gender="m", build=1.3, colors={"torso": 0xfde68a})
_add("aunty", "Bua ji", "family", outfit="saree", hair="long", skin="wheat", gender="f", build=1.15, colors={"torso": 0xbe185d, "drape": 0x6d28d9})
# --- festive / regional ------------------------------------------------------------------------------------
_add("garba_f", "Garba dancer Hetal", "festive", outfit="garba", hair="long", skin="wheat", gender="f", build=0.85)
_add("garba_m", "Garba dancer Jay", "festive", outfit="kurta", hair="short", skin="wheat", gender="m", props=["hat"], build=1.0, colors={"torso": 0xdc2626, "legs": 0xfde68a})
_add("punjabi_m", "Harpreet (Punjabi)", "festive", outfit="turban", hair="short", skin="fair", gender="m", beard=True, build=1.2, colors={"turban": 0xf59e0b})
_add("punjabi_f", "Simran (Lohri)", "festive", outfit="lohri", hair="long", skin="fair", gender="f", build=0.9)
_add("south_m", "Murugan (veshti)", "festive", outfit="southindian", hair="short", skin="dark", gender="m", build=1.05)
_add("south_f", "Lakshmi (Kanjivaram)", "festive", outfit="saree", hair="long", skin="brown", gender="f", build=0.95, colors={"torso": 0x7f1d1d, "drape": 0xfacc15})
_add("bride", "Dulhan Aishwarya", "festive", outfit="saree", hair="bun", skin="fair", gender="f", build=0.85, colors={"torso": 0xb91c1c, "drape": 0xfacc15})
_add("groom", "Dulha Vivaan", "festive", outfit="kurta", hair="short", skin="wheat", gender="m", props=["hat"], build=1.0, colors={"torso": 0xfef3c7, "legs": 0xfef3c7})

PROFILES: list[dict] = [{"id": i, "name": n, "category": c, "spec": {"gender": "m", **s}} for i, n, c, s in _P]
BY_ID = {p["id"]: p for p in PROFILES}
CATEGORIES = {"medical": "Doctor / clinic", "retail": "दुकान / retail", "business": "Business / office", "education": "Teacher / student",
              "fitness": "Gym / salon / spa", "service": "Service / mechanic / delivery", "family": "परिवार", "festive": "त्योहार / regional"}
