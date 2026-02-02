# Research: MARC + ISBN + LCCN/NLMCN Standards


Define the normalization rules and standards used by the harvester.


- ISBN-10 and ISBN-13 validation rules
- MARC 050 (LCCN) parsing: first $a, $b → space
- MARC 060 (NLMCN) parsing: first $a, $b → space
- Subject headings (6XX) rules (stretch)


## 1. Overview of MARC Bibliographic Records

MARC (Machine-Readable Cataloging) is a standardized format used by libraries to encode bibliographic and holdings information. Each MARC record consists of:

•	Fields (identified by a three-digit tag, e.g., 050, 060)

•	Indicators (two characters providing additional meaning)

•	Subfields (identified by a dollar sign $ followed by a letter or number)

For this project, the primary MARC fields of interest are 050 and 060, which contain call numbers.


## 2. MARC Field 050 — Library of Congress Call Number (LCCN)


The MARC 050 field stores the Library of Congress Call Number, which is used by many academic libraries for classification and shelving.

Structure
050  -ind1-ind2- $a classification$ $b -item number-

Relevant Subfields

•	$a — Classification number (mandatory for a valid LCCN)

•	$b — Cutter number and additional item information (optional)

Example

050 10 $aHF5726$b.B27 1980

Normalized Form

HF5726 .B27 1980

Multiple $a Subfields

If multiple $a subfields appear, only the first $a is used.

Example:

050 00 $aZ7164.N3$bL34 no. 9$aZ7165.R42

Normalized result:

Z7164.N3 L34 no. 9



## 3. MARC Field 060 — National Library of Medicine Call Number (NLMCN)


The MARC 060 field stores National Library of Medicine Call Numbers, which are structurally similar to LCCNs but use a different classification system.

Structure

060  -ind1- -ind2- $a -classification- $b -item number-

Subfield Rules

The same subfield rules apply as with MARC 050:

•	$a is required

•	$b is optional

•	Only the first $a is used if multiple exist

Normalization

•	Replace $b with a space

•	Concatenate $a and $b values



## 4. ISBN Standards and Usage

An ISBN (International Standard Book Number) is a unique identifier for books and book-like publications.

Accepted Formats

•	ISBN-10 (10 characters, may end with X)

•	ISBN-13 (13 numeric characters)

Representation Rules

•	ISBNs may include hyphens, which must be removed

•	ISBNs must be treated as text, not numbers

•	Leading zeros must be preserved

Example

978-0-393-04002-9 → 9780393040029

Validation

•	Perform check-digit validation for ISBN-10 and ISBN-13

•	Invalid ISBNs must be written to a separate output file



## 5. Linking ISBNs to Call Numbers

•	ISBNs are used as the lookup key when querying APIs and Z39.50 targets

•	A single ISBN may return:

•	An LCCN

•	An NLMCN

•	Both

•	Neither

•	ISBNs must be checked against the local SQLite database before external lookups



## 6. Normalization Rules (Harvester Requirements)

The harvester must follow these rules when processing call numbers:


LCCN / NLMCN Normalization Rules

•	Always use only the first $a subfield

•	$a is mandatory; records without $a are invalid

•	Replace $b with a single space

•	Preserve spacing and punctuation within subfield values

•	Trim leading and trailing whitespace

•	Resulting call number must be stored as a single string

ISBN Normalization Rules

•	Remove all hyphens

•	Treat ISBNs strictly as text

•	Preserve leading zeros

•	Accept both ISBN-10 and ISBN-13 formats

•	Reject ISBNs that fail check-digit validation


## 7. Validation Requirements

Before accepting a call number:


•	Ensure it originates from a valid MARC 050 or 060 field

•	Ensure $a exists

•	Ensure the normalized call number is not empty

Before attempting external lookups:

•	Check the main SQLite table for an existing entry

•	Check the attempted/failure table within the configured retry window




## 8. Summary

This document defines the authoritative rules for how the LCCN Harvester interprets and normalizes bibliographic data. Following these standards ensures:

•	Consistent output

•	Reliable database entries

•	Interoperability with library systems

•	Compliance with library cataloging practices