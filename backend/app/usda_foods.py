"""Rebuild the public offline catalog from the pinned official Foundation JSON ZIP.

Usage: python -m app.usda_foods /path/to/FoodData_Central_foundation_food_json_2026-04-30.zip
No account, API key, food history or network request is used by this command.
"""
import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path

SOURCE_URL='https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2026-04-30.zip'


def build_catalog(archive_path: Path,output_path: Path):
    with zipfile.ZipFile(archive_path) as archive:
        members=[m for m in archive.infolist() if m.filename.endswith('.json')]
        if len(members)!=1 or members[0].file_size>20_000_000:raise ValueError('Expected one Foundation Foods JSON file under 20 MB')
        payload=json.loads(archive.read(members[0]))
    rows=payload.get('FoundationFoods')
    if not isinstance(rows,list):raise ValueError('Expected the official FoundationFoods schema')
    foods=[];seen=set();skipped=0
    for food in rows:
        if not food:skipped+=1;continue
        identifier=str(food['fdcId'])
        if identifier in seen:raise ValueError('Duplicate USDA identifier')
        seen.add(identifier);nutrients={};warnings=[]
        for value in food.get('foodNutrients') or []:
            if not value or not value.get('nutrient'):continue
            nutrient=value['nutrient'];identifier_n=nutrient['id'];amount=value.get('amount')
            if identifier_n not in (2048,2047,1008,1003,1004,1005):continue
            unit='kcal' if identifier_n in (2048,2047,1008) else 'g'
            if nutrient.get('unitName','').lower()!=unit:raise ValueError('Unexpected USDA nutrient unit')
            if amount is not None and (type(amount) not in (float,int) or not math.isfinite(amount)):raise ValueError('Invalid USDA nutrient amount')
            if amount is not None and amount<0:
                warnings.append(f"USDA reports negative {nutrient['name']}; retained as unknown, not zero.")
                amount=None
            nutrients[identifier_n]=amount
        energy=next((nutrients[k] for k in (2048,2047,1008) if nutrients.get(k) is not None),None)
        foods.append({'id':identifier,'name':food['description'],'calories_kcal':energy,'protein_grams':nutrients.get(1003),'fat_grams':nutrients.get(1004),'carbohydrate_grams':nutrients.get(1005),**({'warnings':warnings} if warnings else {})})
    result={'source':'USDA FoodData Central Foundation Foods','release':'2026-04-30','url':SOURCE_URL,
            'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            'basis':'per 100 g edible portion; energy prioritizes specific Atwater, general Atwater, then reported kcal','foods':foods}
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    return {'foods':len(foods),'empty_source_records':skipped,'archive_sha256':result['archive_sha256']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'resources/usda-foundation.json')
    args=parser.parse_args();print(json.dumps(build_catalog(args.archive,args.output)))
