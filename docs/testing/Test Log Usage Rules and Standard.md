# Test Log Usage Rules and Standards for LCCN Harvester Project

### General Usage Rules

**- Each row in the test log represents one test case execution.**

**- Test cases must not be deleted expected result should be updated instead.**

**- One function may have many tests, 1 to many relationships.**

**- But one test cannot have many functions being tested.**

1.	**Test ID**

Each test has its own ID.

2.	**Sprint Week**

Working Sprint

3.	**Tester name**

Person doing the testing

4.	**Feature / Requirement**

Small explanation saying what we trying to accomplish with this feature

    Ex: Validate harvest is properly handling user interrupts. 

5.  **Test Description**

Small explanation saying how this feature will be tested. 

    Ex: Testing by uploading list of Invalid and ISBNs to check ISBN validator. 
6.	**Input Data**

I can be a user input, file upload, or button click. 

    Ex: Input is mouse and keyboard to save configuration settings.
7. **Expected Result**

Whatever the passing testing result should be:

    Ex: Returning list of invalid ISBNs only.

8. **Actual Result**

Whatever the last testing result is:

    Ex: Return list of invalid ISBNs only and some valid ISBNs.

9.	**Pass / Fail**

Everything is a fail until it passes.


10.  **Date Tested**

When the first test was done

    Ex: DD/MM/YYYY we use this format

11.  **Date Passe**

When the last test(passing test) was done

Can be same day if passed without fixing.


12.  **Notes**

Any notes to mention for the test. 
