def get_values_from_line(line):
    """
    Extracts every number from a string and puts each number in a list in the order they are presented in the string.

    :param line: String in which its numbers will be extracted from.
    :return: A list of numbers that are from the inputted string.
    """
    value = 0
    list_to_store = []
    for i in range(len(line)):
        if line[i].isdigit():
            value *= 10
            value += int(line[i])
        if line[i] == 'l':
            value *= 10
            value += 1
        if line[i] == 'o' or line[i] == 'O':
            value *= 10
        if line[i] == 's' or line[i] == 'S':
            value *= 10
            value += 5
        if value and ((not line[i].isdigit() and (
                line[i] != 'l' or line[i] != 'o' or line[i] != 'O' or line[i] != 's' or line[i] != 'S')) or
                      i + 1 == len(line)):
            list_to_store.append(three_digits_long(value))
            value = 0
    return list_to_store


def three_digits_long(number):
    """
    Floor divides a number until at most 3 digits long.

    :param number: Number to be reduced to 3 digits
    :return: The original number, but only containing the first 3 digits
    """
    if number > 999:
        return three_digits_long(number // 10)
    return number


def min_y_from_vertices(vertices):
    """
    Given the bounding box of a text in an image, this method returns the smallest y value of the four vertices.

    :param vertices: Bounding box of the text in question.
    :return: smallest y value, representing the number of pixels from the top of the image to the top of the text.
    """
    min_y = vertices[0].y
    for i in range(1, 4):
        min_y = min(min_y, vertices[i].y)
    return min_y


def get_user_input_from_message(message):
    """
    Gets the custom user value the user inputs when using a command. If no value exists, it will return an empty string.

    :param message: Message the user typed, given as a string.
    :return: Everything after the space that separates the command from the user input
    """
    result = message.split()
    if len(result) < 2:
        return ''

    return result[1]


