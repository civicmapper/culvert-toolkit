FREQUENCIES = [1,2,5,10,25,50,100,200,500,1000]

QP_PREFIX = 'Y'

QP_HEADER = ['{0}{1}'.format(QP_PREFIX, f) for f in FREQUENCIES]

NOAA_RAINFALL_REGION_LOOKUP = {
    "sa":"1: Semiarid Southwest",
    "orb":"2: Ohio River Basin and Surrounding States",
    "pr":"3: Puerto Rico and the U.S. Virgin Islands",
    "hi":"4: Hawaiian Islands",
    "pi":"5: Selected Pacific Islands",
    "sw":"6: California",
    "ak":"7: Alaska",
    "mw":"8: Midwestern States",
    "se":"9: Southeastern States",
    "ne":"10: Northeastern States",
    "tx":"11: Texas"
}

VALIDATION_ERRORS_FIELD_LENGTH = 1024