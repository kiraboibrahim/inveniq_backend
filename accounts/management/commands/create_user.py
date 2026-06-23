from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

User = get_user_model()

ROLE_CHOICES = ["admin", "manager", "staff"]


class Command(BaseCommand):
    help = "Creates a new user for InvenIQ with a specific role. Prompts for any value not passed as a flag."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, help="Email address for the new user")
        parser.add_argument(
            "--first-name", type=str, default=None, help="User's first name"
        )
        parser.add_argument(
            "--last-name", type=str, default=None, help="User's last name"
        )
        parser.add_argument(
            "--role",
            type=str,
            choices=ROLE_CHOICES,
            default=None,
            help="User's role (admin, manager, staff)",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Make the user a Django superuser",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Don't prompt for missing values; fail instead if any are missing.",
        )

    def handle(self, *args, **options):
        interactive = options["interactive"]

        email = options["email"] or self._prompt_email(interactive)
        first_name = (
            options["first_name"]
            if options["first_name"] is not None
            else self._prompt("First name", interactive, default="")
        )
        last_name = (
            options["last_name"]
            if options["last_name"] is not None
            else self._prompt("Last name", interactive, default="")
        )
        is_superuser = options["superuser"]

        if is_superuser:
            role = "admin"
        else:
            role = options["role"] or self._prompt_role(interactive)

        password = self._prompt_password(interactive)

        try:
            if is_superuser:
                User.objects.create_superuser(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully created superuser: {email}")
                )
            else:
                User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully created {role} user: {email}")
                )

        except IntegrityError:
            raise CommandError(f"User with email '{email}' already exists.")
        except ValidationError as e:
            raise CommandError(f"Invalid input: {'; '.join(e.messages)}")
        except Exception as e:
            raise CommandError(f"An error occurred while creating the user: {str(e)}")

    def _prompt(self, label, interactive, default=""):
        if not interactive:
            return default
        value = input(f"{label} [{default or 'optional'}]: ").strip()
        return value or default

    def _prompt_email(self, interactive):
        if not interactive:
            raise CommandError("--email is required when using --noinput.")
        while True:
            email = input("Email: ").strip()
            if email:
                return email
            self.stderr.write("Email cannot be empty.")

    def _prompt_role(self, interactive):
        if not interactive:
            return "staff"
        choices_display = "/".join(ROLE_CHOICES)
        while True:
            role = (
                input(f"Role ({choices_display}) [staff]: ").strip().lower() or "staff"
            )
            if role in ROLE_CHOICES:
                return role
            self.stderr.write(f"Role must be one of: {choices_display}")

    def _prompt_password(self, interactive):
        if not interactive:
            raise CommandError(
                "--noinput was set, but password must always be entered interactively."
            )
        while True:
            password = getpass("Password: ")
            if not password:
                self.stderr.write("Password cannot be empty.")
                continue
            confirm = getpass("Confirm password: ")
            if password != confirm:
                self.stderr.write("Passwords didn't match. Try again.")
                continue
            return password
