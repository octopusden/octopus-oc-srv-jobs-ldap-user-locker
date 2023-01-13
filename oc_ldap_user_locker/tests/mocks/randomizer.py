import string
import random

class Randomizer(object):
    def random_digits(self, min_len, max_len = None):
        if not max_len:
            max_len = min_len

        result = ""
        for idx in range(0, random.randint(min_len, max_len)):
            result = u"%s%d" % (result, random.randint(0,9))

        return result

    def random_str(self, min_len, max_len = None):
        if not max_len:
            max_len = min_len

        result = ""

        result_len = random.randint(min_len, max_len)

        for idx in range(0, result_len):
            result += random.choice(string.ascii_letters + string.digits)

        return result

    def random_letters(self, min_len, max_len = None):
        if not max_len:
            max_len = min_len

        result = ""

        result_len = random.randint(min_len, max_len)

        for idx in range(0, result_len):
            result += random.choice(string.ascii_letters)

        return result


    def random_number(self, n_min=0, n_max=1):
        # proxy method to get rid of importing random module in another places
        return random.randint(n_min, n_max)
