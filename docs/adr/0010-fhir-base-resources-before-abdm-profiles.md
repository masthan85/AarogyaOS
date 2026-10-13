# ADR-0010 Export base FHIR R4 first; add ABDM profiles only after reading the IG
Status: accepted. The ABDM profile guide could not be read, and profile rules (required elements, value sets,
Composition types) change between versions. Emitting `meta.profile` without meeting those rules would be a false claim
of conformance. So the mapping layer produces plain R4 resources and says so in its CapabilityStatement; a later profile
layer can add constraints and `meta.profile` per resource. Cost: the output cannot yet be submitted to ABDM.
