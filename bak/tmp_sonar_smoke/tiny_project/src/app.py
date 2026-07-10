# Tiny sample project for SonarQube smoke testing

def calculate_discount(price, user_type):
    # This intentionally has simple branching so SonarQube has something to analyze
    if user_type == "student":
        return price * 0.8
    elif user_type == "staff":
        return price * 0.7
    elif user_type == "vip":
        return price * 0.6
    else:
        return price


def format_user_message(name, price):
    # This intentionally duplicates similar formatting logic
    message = "Hello " + name + ", your price is " + str(price)
    return message


def format_admin_message(name, price):
    # This intentionally duplicates similar formatting logic
    message = "Hello " + name + ", your price is " + str(price)
    return message


def main():
    # This intentionally uses a simple hard-coded value for smoke testing only
    user_name = "test-user"
    price = calculate_discount(100, "student")
    print(format_user_message(user_name, price))


if __name__ == "__main__":
    main()
