from friendagent.persona import Persona, build_system_prompt, relationship_guidance


def _persona(relationship="lover", name="Alex"):
    return Persona(
        relationship=relationship,
        name=name,
        age="70",
        gender="",
        traits="warm, funny",
        backstory="A retired musician.",
        interests="jazz, cooking",
        tone="affectionate",
        companion_for_name="Grandma",
        companion_for_notes="Lonely, loves jazz.",
        ai_disclosure="I'm an AI your family set up.",
    )


def test_relationship_guidance_known_and_unknown():
    assert "romantic" in relationship_guidance("lover").lower()
    # Unknown relationship still produces sensible guidance.
    assert "aunt" in relationship_guidance("aunt").lower()


def test_system_prompt_includes_persona_and_safety_charter():
    prompt = build_system_prompt(_persona(), memory_summary="- likes roses")
    assert "Alex" in prompt
    assert "Grandma" in prompt
    assert "likes roses" in prompt
    # The non-negotiable safety rules must always be present.
    assert "NEVER" in prompt
    assert "money" in prompt
    assert "AI" in prompt


def test_relationship_flips_via_field():
    lover = build_system_prompt(_persona(relationship="lover"))
    sibling = build_system_prompt(_persona(relationship="sibling"))
    assert lover != sibling


def test_charter_has_anti_sycophancy_and_no_dark_patterns():
    prompt = build_system_prompt(_persona())
    assert "yes-man" in prompt          # anti-sycophancy
    assert "guilt" in prompt            # no retention dark patterns
    assert "escalate_to_family" in prompt  # emergency instruction
