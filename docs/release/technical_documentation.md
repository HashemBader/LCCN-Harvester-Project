# Technical Documentation

## Purpose
Developer-facing overview: architecture, DB, config, and how to run from source.

## Content (to fill)
- Architecture diagram
- Component overview
- DB schema
- Config files
- Build/run steps


## isbn_validator.py
This function is meant to make sure the ISBN that are coming are first properly formatted (normalized). 

- It takes an ISBN from the user
- Then normalizes it and passes it to the validator if it is correct.
- Or goes to the invalid ISBN log file.

And then they can be validated using the checksum to make sure each number is correct.

## call_number_normalizer.py
This function is meant to make sure that the call numbers from the APIs returns are properly formatted and no characters are missing.

And removes the trailing and leading characters as needed.

## lccn_validator.py
This function is meant to make sure the lc call number we are getting are complain with the standard MARC 050 formatting.

## nlmcn_validator.py
This function is meant to make sure the lc call number we are getting are complain with the standard MARC 060 formatting.

## marc_parser.py
This function reads the data from the XML and JSON files that the APIs return and formats so they can be read efficiently by the system.