from enum import Enum as PyEnum


class VerificationStatusEnum(str, PyEnum):
    DENIED = "denied"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"


class SmokingAttitudeEnum(str, PyEnum):
    NON_SMOKER = "Не курю"
    SOMETIMES = "Иногда на вечеринках"
    REGULAR_SMOKER = "Любитель/Любительница сигарет"
    TRYING_TO_QUIT = "В поисках силы воли"
    NOT_OPPOSED = "Не против, но предпочитаю не курить"
    STYLE_LIFE = "Тату и сигареты"


class AlcoholAttitudeEnum(str, PyEnum):
    ABSTAIN = "Безалкогольный образ жизни"
    ENJOY_SIP = "Люблю посидеть за бокалом"
    PARTY_EVERY_DAY = "Вечеринка каждый день"
    MODERATE = "Умеренно"
    COCKTAIL_MASTER = "Коктейльный мастер"
    HERBAL_TEA = "Травяной чай и безалкогольные напитки"


class WhatLookingForEnum(str, PyEnum):
    TRUE_LOVE = "Истинная любовь"
    NEW_FRIENDS = "Новые друзья"
    ADVENTURES = "Приключения и веселье"
    SERIOUS_RELATIONSHIP = "Серьёзные отношения с перспективой брака"
    TRAVEL = "Путешествия вместе"
    UNDERSTANDING = "Взаимопонимание и поддержка"
    FRIENDSHIP_WITH_BENEFITS = "Дружба с выгодой"


class ReligionEnum(str, PyEnum):
    ATHEIST = "Атеист/Атеистка"
    ORTHODOX = "Православный/Православная"
    CATHOLIC = "Католик/Католичка"
    MUSLIM = "Мусульманин/Мусульманка"
    BUDDHIST = "Буддист/Буддистка"
    HINDU = "Индуист/Индуистка"
    SPIRITUAL = "Духовно, но не религиозен(на)"
    JUDAIST = "Иудаист/Иудаистка"
    OTHER = "Другие религии"
    PREFERS_NOT_TO_SAY = "Предпочитаю не указывать"


class ChildrenEnum(str, PyEnum):
    PLANNING_CHILDREN = "Планирую детей в будущем"
    HAVE_CHILDREN = "Есть дети, и они занимают моё сердце"
    CHILDREN_OUTGROWN = "Дети уже выросли и самостоятельны"
    OPEN_TO_PARTNER_CHILDREN = "Не против детей у партнера"
    NO_CHILDREN = "Нет детей, и это меня устраивает"


class AppearanceEnum(str, PyEnum):
    ACTIVE_LIFESTYLE = "Активный образ жизни и забота о теле."
    FASHION_FORWARD = "Люблю моду и следую последним трендам."
    NATURAL_SIMPLE = "Предпочитаю натуральный и простой вид."
    REFINED_STYLE = "Обожаю изысканный и утончённый стиль."
    TATTOO_PIERCING = "Носитель татуировок и пирсинга."
    TIMELY_CLASSIC = "Предпочитаю вечную классику в одежде и внешности."
    EXPERIMENTAL_STYLE = "Люблю выделяться и экспериментировать со стилем."
    SOFT_KIND_APPEARANCE = "Внешность отражает мягкость и доброту."
