"""
Clinic Appointment System Mini Project
P = 9, so P % 4 == 1: Emergency booking twist
"""

from abc import ABC, abstractmethod
from enum import Enum


# Exceptions

class ClinicError(Exception):
    """Base class for expected clinic-rule errors."""


class ValidationError(ClinicError):
    pass


class BookingError(ClinicError):
    pass


class AppointmentStateError(ClinicError):
    pass


class LoggingError(ClinicError):
    pass


#  Clock

class Clock(ABC):
    """Interface used by the domain instead of reading the computer clock"""

    @abstractmethod
    def now(self):
        """Return the current hour as an integer from 0 to 168."""
        raise NotImplementedError


class ManualClock(Clock):
    """A controllable clock useful for repeatable tests and demonstrations."""

    def __init__(self, current_hour):
        self.set_hour(current_hour)

    def now(self):
        return self._hour

    def set_hour(self, hour):
        if not isinstance(hour, int) or not 0 <= hour <= 168:
            raise ValidationError("Clock hour must be a whole number from 0 to 168.")
        self._hour = hour


#  People and staff

class Person(ABC):
    """Abstract base class shared by everyone in the clinic."""

    _person_constructor_calls = 0

    def __init__(self, name, person_id):
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("Name cannot be empty.")
        if not isinstance(person_id, int) or person_id <= 0:
            raise ValidationError("Person id must be a positive whole number.")

        self.__name = name.strip()
        self.__id = person_id
        Person._person_constructor_calls += 1

    @property
    def name(self):
        return self.__name

    @property
    def id(self):
        return self.__id

    @abstractmethod
    def role(self):
        raise NotImplementedError

    @classmethod
    def reset_constructor_counter(cls):
        Person._person_constructor_calls = 0

    @classmethod
    def constructor_count(cls):
        return Person._person_constructor_calls


class Patient(Person):
    def __init__(self, name, person_id, emergency=False):
        super().__init__(name, person_id)
        self.__emergency = bool(emergency)

    def role(self):
        return "Patient"

    @property
    def is_emergency(self):
        return self.__emergency

    def flag_emergency(self):
        self.__emergency = True


class Staff(Person, ABC):
    def __init__(self, name, person_id, p=9, **kwargs):
        if not isinstance(p, int) or p < 0:
            raise ValidationError("P must be a non-negative whole number.")
        self.__p = p
        # Cooperative super() supports the Doctor/Lecturer diamond below
        super().__init__(name, person_id, **kwargs)

    @property
    def p(self):
        return self.__p

    @abstractmethod
    def fee(self):
        raise NotImplementedError


class Doctor(Staff):
    def role(self):
        return "Doctor"

    def fee(self):
        return 40 + 5 * (self.p % 5)


class Nurse(Staff):
    def role(self):
        return "Nurse"

    def fee(self):
        return 10 + (self.p % 3)


class Pharmacist(Staff):
    def role(self):
        return "Pharmacist"

    def fee(self):
        return 5


class Lecturer(Person, ABC):


    def __init__(self, name, person_id, module_name, **kwargs):
        if not isinstance(module_name, str) or not module_name.strip():
            raise ValidationError("Module name cannot be empty.")
        self.__module_name = module_name.strip()
        super().__init__(name, person_id, **kwargs)

    @property
    def module_name(self):
        return self.__module_name


class MedicalLecturer(Doctor, Lecturer):
    """
    A Doctor and Lecturer. The cooperative super() chain reaches Person once
    Doctor's fee implementation is inherited so this person receives the
    Doctor fee rather than a separate lecturer fee.
    """

    def __init__(self, name, person_id, module_name, p=9):
        super().__init__(
            name=name,
            person_id=person_id,
            p=p,
            module_name=module_name
        )

    def role(self):
        return "Doctor and Lecturer"


# ---------------------------- Appointment ----------------------------

class AppointmentStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# Appointment key details:
# 1. id is a positive integer and unique within its Clinic.
# 2. start_hour is a whole number from 0 to 168.
# 3. Each appointment lasts exactly one hour.
# 4. patient and staff are present and cannot be replaced after creation.
# 5. Status is always PENDING, CONFIRMED, or CANCELLED.
# 6. Legal transitions are PENDING - CONFIRMED, PENDING -CANCELLED,
#    and CONFIRMED -> CANCELLED. CANCELLED is terminal.
# 7. A confirmed appointment cannot be cancelled less than 2 hours before
#    its start, and no appointment can be cancelled at or after its start.
class Appointment:
    def __init__(self, appointment_id, patient, staff, start_hour):
        if not isinstance(appointment_id, int) or appointment_id <= 0:
            raise ValidationError("Appointment id must be positive.")
        if not isinstance(start_hour, int) or not 0 <= start_hour <= 168:
            raise ValidationError("Start hour must be a whole number from 0 to 168.")
        if patient is None or staff is None:
            raise ValidationError("An appointment needs a patient and a staff member.")

        self.__id = appointment_id
        self.__patient = patient
        self.__staff = staff
        self.__start_hour = start_hour
        self.__status = AppointmentStatus.PENDING
        self.__cancel_reason = None

    @property
    def id(self):
        return self.__id

    @property
    def patient(self):
        return self.__patient

    @property
    def staff(self):
        return self.__staff

    @property
    def start_hour(self):
        return self.__start_hour

    @property
    def end_hour(self):
        return self.__start_hour + 1

    @property
    def status(self):
        return self.__status

    @property
    def cancel_reason(self):
        return self.__cancel_reason

    @property
    def price(self):
        return self.__staff.fee()

    def confirm(self):
        if self.__status is not AppointmentStatus.PENDING:
            raise AppointmentStateError(
                "Only a PENDING appointment can be confirmed."
            )
        self.__status = AppointmentStatus.CONFIRMED

    def cancel(self, now, reason="cancelled"):
        if self.__status is AppointmentStatus.CANCELLED:
            raise AppointmentStateError("A cancelled appointment cannot change again.")
        if now >= self.__start_hour:
            raise AppointmentStateError("appointment has already started.")
        if (
            self.__status is AppointmentStatus.CONFIRMED
            and self.__start_hour - now < 2
        ):
            raise AppointmentStateError("too late: confirmed appointments need 2 hours' notice.")

        self.__status = AppointmentStatus.CANCELLED
        self.__cancel_reason = reason


#  Logging

class AppointmentLogger:
    """
    Context manager: one open and one close per Clinic session.
    The file is closed in finally, even if an operation or a log write fails.
    """

    def __init__(self, filename):
        self._filename = filename
        self._file = None
        self._opened = False
        self._closed = False

    def __enter__(self):
        if self._opened:
            raise LoggingError("The appointment log has already been opened.")
        try:
            self._file = open(self._filename, "a", encoding="utf-8")
            self._opened = True
            self._write_line("[log] opened")
            print("[log] opened")
            return self
        except OSError as exc:
            if self._file is not None:
                self._file.close()
            raise LoggingError(f"Could not open appointment log: {exc}") from exc

    def write(self, message):
        if self._file is None or self._closed:
            raise LoggingError("The appointment log is not open.")
        try:
            self._write_line(message)
        except OSError as exc:
            raise LoggingError(f"Could not write to appointment log: {exc}") from exc

    def _write_line(self, message):
        self._file.write(message + "\n")
        self._file.flush()

    def __exit__(self, exc_type, exc_value, traceback):
        if self._closed:
            return False

        close_error = None
        try:
            if self._file is not None:
                try:
                    self._write_line("[log] closed")
                except OSError as exc:
                    close_error = exc
        finally:
            if self._file is not None:
                try:
                    self._file.close()
                except OSError as exc:
                    close_error = close_error or exc
            self._closed = True
            print("[log] closed")

        if close_error is not None and exc_type is None:
            raise LoggingError(f"Could not finish appointment log: {close_error}")
        return False


#  Clinic

# Clinic key detailss:
# 1. Every registered person id and appointment id is unique across the Clinic.
# 2. A patient can have at most one non-cancelled appointment at a givn hour
# 3. A staff member can have at most one non-cancelled appointment at a given hour.
# 4. All appointments are stored internally; callers receive an immutable tuple
# 5. Every Clinic action is logged, including failed actions.
# 6. Emergency bookings may replace only a PENDING appointment for the same
#    staff member and hour. CONFIRMED appointments are never bumped.
class Clinic:
    def __init__(self, clock, log_filename="appointment.log"):
        if clock is None:
            raise ValidationError("Clinic requires a Clock object.")
        self.__clock = clock
        self.__patients = []
        self.__staff = []
        self.__appointments = []
        self.__used_ids = set()
        self.__next_appointment_id = 1000
        self.__logger = AppointmentLogger(log_filename)
        self.__session_open = False

    def __enter__(self):
        self.__logger.__enter__()
        self.__session_open = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__session_open = False
        return self.__logger.__exit__(exc_type, exc_value, traceback)

    @property
    def appointments(self):
        return tuple(self.__appointments)

    @property
    def staff_members(self):
        return tuple(self.__staff)

    @property
    def patients(self):
        return tuple(self.__patients)

    def _log(self, message):
        if not self.__session_open:
            raise LoggingError("Use Clinic inside a 'with' block so the log is open.")
        self.__logger.write(message)

    def _perform(self, label, operation):
        """Run one action and log both success and failure."""
        try:
            result = operation()
            self._log(f"{label}: SUCCESS")
            return result
        except Exception as exc:
            # The failure is logged before the original error is re-raised.
            try:
                self._log(f"FAILED {label}: {exc}")
            except LoggingError:
                # A logging failure must not hide the original domain error.
                pass
            raise

    def add_patient(self, patient):
        def action():
            if patient.id in self.__used_ids:
                raise ValidationError(f"Duplicate id {patient.id}.")
            self.__used_ids.add(patient.id)
            self.__patients.append(patient)
            return patient
        return self._perform(f"register patient #{patient.id}", action)

    def add_staff(self, staff_member):
        def action():
            if staff_member.id in self.__used_ids:
                raise ValidationError(f"Duplicate id {staff_member.id}.")
            self.__used_ids.add(staff_member.id)
            self.__staff.append(staff_member)
            return staff_member
        return self._perform(f"register {staff_member.role()} #{staff_member.id}", action)

    def _allocate_appointment_id(self):
        while self.__next_appointment_id in self.__used_ids:
            self.__next_appointment_id += 1
        new_id = self.__next_appointment_id
        self.__used_ids.add(new_id)
        self.__next_appointment_id += 1
        return new_id

    def _active_conflicts(self, person, hour):
        return [
            appointment for appointment in self.__appointments
            if appointment.status is not AppointmentStatus.CANCELLED
            and appointment.start_hour == hour
            and (
                appointment.patient.id == person.id
                or appointment.staff.id == person.id
            )
        ]

    def book(self, patient, staff_member, start_hour):
        label = f"book {patient.name} with {staff_member.name} at hour {start_hour}"

        def action():
            if patient not in self.__patients:
                raise BookingError("Patient is not registered with this Clinic.")
            if staff_member not in self.__staff:
                raise BookingError("Staff member is not registered with this Clinic.")
            if not isinstance(start_hour, int) or not 0 <= start_hour <= 168:
                raise ValidationError("Start hour must be a whole number from 0 to 168.")

            # A patient conflict cannot be solved by bumping another patient.
            patient_conflicts = [
                a for a in self.__appointments
                if a.patient.id == patient.id
                and a.start_hour == start_hour
                and a.status is not AppointmentStatus.CANCELLED
            ]
            if patient_conflicts:
                raise BookingError("Patient already has an appointment at that hour.")

            staff_conflicts = [
                a for a in self.__appointments
                if a.staff.id == staff_member.id
                and a.start_hour == start_hour
                and a.status is not AppointmentStatus.CANCELLED
            ]

            if staff_conflicts:
                if not patient.is_emergency:
                    raise BookingError("Staff member is already booked at that hour.")

                # The emergency twist can bump PENDING, but never CONFIRMED.
                for conflict in staff_conflicts:
                    if conflict.status is AppointmentStatus.CONFIRMED:
                        raise BookingError("Emergency booking cannot bump a CONFIRMED appointment.")
                    if conflict.status is AppointmentStatus.PENDING:
                        conflict.cancel(self.__clock.now(), reason="bumped")
                        self._log(
                            f"appointment #{conflict.id} CANCELLED: bumped by emergency booking"
                        )

            appointment_id = self._allocate_appointment_id()
            appointment = Appointment(
                appointment_id, patient, staff_member, start_hour
            )
            self.__appointments.append(appointment)
            self._log(
                f"appointment #{appointment.id} CREATED: {patient.name}, "
                f"{staff_member.name}, hour {start_hour}, PENDING"
            )
            return appointment

        return self._perform(label, action)

    def confirm(self, appointment_id):
        def action():
            appointment = self._find_appointment(appointment_id)
            appointment.confirm()
            return appointment
        return self._perform(f"confirm appointment #{appointment_id}", action)

    def cancel(self, appointment_id, reason="cancelled"):
        def action():
            appointment = self._find_appointment(appointment_id)
            appointment.cancel(self.__clock.now(), reason)
            return appointment
        return self._perform(f"cancel appointment #{appointment_id}", action)

    def _find_appointment(self, appointment_id):
        for appointment in self.__appointments:
            if appointment.id == appointment_id:
                return appointment
        raise BookingError(f"Appointment #{appointment_id} was not found.")

    def print_staff_fees(self):
        """
        Polymorphism:every Staff subclass supplies role() and fee().
        """
        print("\nStaff roles and fees:")
        for staff_member in self.__staff:
            print(f"{staff_member.role()}: ${staff_member.fee()}")

    def print_appointments(self):
        print("\nAppointment summary:")
        for appointment in self.__appointments:
            print(
                f"#{appointment.id}: {appointment.patient.name} with "
                f"{appointment.staff.name}, hour {appointment.start_hour}, "
                f"{appointment.status.value}, fee ${appointment.price}"
                + (
                    f", reason={appointment.cancel_reason}"
                    if appointment.cancel_reason else ""
                )
            )


#  Demo

def main():
    # P = 9: 9 % 4 = 1, so the selected twist is Emergency booking.
    P = 9
    print(f"Selected P = {P}; P mod 4 = {P % 4} (Emergency booking)")

    # Demonstrate that the Person constructor runs once in the diamond.
    Person.reset_constructor_counter()
    medical_lecturer = MedicalLecturer(
        "Dr Aaron William", 6, "Health Informatics", p=P
    )
    print(
        "Person constructor calls for MedicalLecturer:",
        Person.constructor_count()
    )
    print(
        f"{medical_lecturer.role()} | module: {medical_lecturer.module_name} "
        f"| fee: ${medical_lecturer.fee()}"
    )

    clock = ManualClock(5)

    with Clinic(clock, "appointment.log") as clinic:
        # Register patients.
        patient_a = Patient("Hulengende", 1)
        emergency_patient = Patient("Rudo", 2, emergency=True)
        patient_c = Patient("Kundai", 3)

        clinic.add_patient(patient_a)
        clinic.add_patient(emergency_patient)
        clinic.add_patient(patient_c)

        # Register staff. MedicalLecturer is also a Doctor/Staff object.
        doctor = Doctor("Dr Trinity", 10, p=P)
        nurse = Nurse("Nurse Dube", 11, p=P)
        pharmacist = Pharmacist("Pharmacist Ncube", 12, p=P)

        clinic.add_staff(doctor)
        clinic.add_staff(nurse)
        clinic.add_staff(pharmacist)
        clinic.add_staff(medical_lecturer)

        # One loop demonstrates polymorphism for all staff subclasses.
        clinic.print_staff_fees()

        # Normal pending appointment, then emergency patient bumps it.
        first = clinic.book(patient_a, doctor, 10)
        replacement = clinic.book(emergency_patient, doctor, 10)
        print(
            f"\nEmergency result: appointment #{first.id} is "
            f"{first.status.value} ({first.cancel_reason}); "
            f"new appointment #{replacement.id} is {replacement.status.value}."
        )

        # Confirmed appointment:emergency booking must NOT bump it.
        confirmed = clinic.book(patient_c, nurse, 12)
        clinic.confirm(confirmed.id)
        try:
            clinic.book(emergency_patient, nurse, 12)
        except BookingError as error:
            print("Expected failed emergency booking:", error)

        # Confirmed cancellation with less than two hours' notice must fail.
        clock.set_hour(11)
        try:
            clinic.cancel(confirmed.id, reason="patient request")
        except AppointmentStateError as error:
            print("Expected failed cancellation:", error)

        clinic.print_appointments()

    print("\nDemo complete. Check appointment.log for successful and failed actions.")


if __name__ == "__main__":
    main()
