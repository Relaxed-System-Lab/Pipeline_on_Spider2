from llm.LLM import QWQ as model
import json
from tqdm import tqdm
from configs.Instruction import TABLE_AUG_INSTRUCTION, SQL_GENERATION_INSTRUCTION
import argparse
import sys
import os
import torch
sys.path.append(".")
from configs.config import model_path, cuda_visible

os.environ["HF_DATASETS_CACHE"] = model_path
os.environ["HF_HOME"] = model_path
os.environ["HF_HUB_CACHE"] = model_path
os.environ["CUDA_VISIBLE_DEVICES"] = cuda_visible


def table_info_construct(ppl):
    (question, simple_ddl, ddl_data,
     foreign_key, evidence, example) = (ppl['question'].strip(), ppl['simplified_ddl'].strip(),
                                        ppl['ddl_data'].strip(), ppl['foreign_key'].strip(),
                                        ppl['evidence'].strip(), ppl['example'])

    table_info = ('### Sqlite SQL tables, with their properties:\n' + simple_ddl +
                  '\n### Here are some data information about database references.\n' + ddl_data +
                  '\n### Foreign key information of Sqlite SQL tables, used for table joins:\n' + foreign_key)
    return table_info


def table_column_selection(table_info, ppl):
    torch.cuda.empty_cache()
    qwq = model()
    evidence = ppl['evidence'].strip()
    question = ppl['question'].strip()
    json_prompt = '''Respond only with valid json. Do not write an introduction or summary.
    The format is {"tables": ["table1", "table2", ...],"columns":["table1.`column1`","table2.`column2`",...]}
    '''
    prompt_table = table_info.strip() + '\n\n' + '### definition: ' + evidence + "\n### Question: " + question
    prompt = prompt_table + '\n\n' + json_prompt
    table_column = qwq(TABLE_AUG_INSTRUCTION, prompt)
    table_column = json.loads(table_column)
    return table_column


def preliminary_sql(table_info, table_column, ppl):
    torch.cuda.empty_cache()
    qwq = model()
    example = ppl['example']
    evidence = ppl['evidence'].strip()
    question = ppl['question'].strip()
    json_prompt = '''Respond only with valid json. Do not write an introduction or summary.
    The format is {"sql": "SQL statement that meets the user's question requirements"}
    '''
    table_info += f'### tables: {table_column["tables"]}\n'
    table_info += f'### columns: {table_column["columns"]}\n'

    table_info = example.strip() + "\n\n### Answer the question by sqlite SQL query only and with no explanation. You must minimize SQL execution time while ensuring correctness.\n" + table_info.strip() + '\n\n### definition: ' + evidence + "\n### Question: " + question
    prompt = table_info + '\n\n' + json_prompt
    
    answer = qwq(SQL_GENERATION_INSTRUCTION, prompt)
    try:
        answer = json.loads(answer)
    except Exception as e:
        print(e)
        answer = answer.replace("\\", "\\\\")
        answer = json.loads(answer)
    answer = answer['sql'].replace('\n', ' ')
    return answer


def main(ppl_file, output_file, info_file, x=0):
    # 1.加载prompt信息 从0开始
    with open(ppl_file, 'r') as f:
        ppls = json.load(f)

    answers = []
    informations = []

    # for i in tqdm(range(x, len(ppls))):
    # Try first 128 questions for now
    for i in tqdm(range(x, 128)):
        information = {}
        ppl = ppls[i]

        # table_info
        table_info = table_info_construct(ppl)

        #  table_column
        table_column = table_column_selection(table_info, ppl)
        information['tables'] = table_column['tables']
        information['columns'] = table_column['columns']
        informations.append(information)

        # preliminary_sql
        pre_sql = preliminary_sql(table_info, table_column, ppl)
        answers.append(pre_sql)

        if not os.path.exists(output_file):
            open(output_file, 'w', encoding='utf-8').close()

        with open(output_file, 'w', encoding='utf-8') as file:
            for sql in answers:
                file.write(str(sql) + '\n')

        # Ensure the info file exists
        if not os.path.exists(info_file):
            open(info_file, 'w', encoding='utf-8').close()

        with open(info_file, 'w', encoding='utf-8') as file:
            json.dump(informations, file, indent=4, ensure_ascii=False)


if __name__ == '__main__':
    # 创建 ArgumentParser 对象
    parser = argparse.ArgumentParser()

    # 添加命令行选项

    ## 这里的dataset是ppl_dev.json
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--ppl_file", type=str, default="src/information/ppl_dev.json")
    parser.add_argument("--sql_out_file", type=str, default="src/sql_log/preliminary_sql.txt")
    parser.add_argument("--Schema_linking_LLM", type=str, default="src/schema_linking/LLM.json")
    # 解析命令行参数
    args = parser.parse_args()

    main(args.ppl_file, args.sql_out_file, args.Schema_linking_LLM, args.start_index)
