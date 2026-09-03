from importer.parsers.itemdbname import parse

SAMPLE = (
    'ItemDBNameTbl = {Gray_Shard = 6672, Thanos_Sword = 13441, '
    'Thanos_Knuckle = 1836, Thanos_TSword_AD = 600016}'
)


def test_parse_itemdbname():
    result = parse(SAMPLE)
    assert result == {
        "Gray_Shard": 6672,
        "Thanos_Sword": 13441,
        "Thanos_Knuckle": 1836,
        "Thanos_TSword_AD": 600016,
    }
