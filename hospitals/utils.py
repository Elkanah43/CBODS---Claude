def staff_hospital(user):
    """The hospital a staff user belongs to, or None."""
    profile = getattr(user, "staff_profile", None)
    return profile.hospital if profile else None
