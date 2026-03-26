from shared_application_services import BaseDTO


class SubmitAdCodeRequest(BaseDTO):
    ad_codes: str
