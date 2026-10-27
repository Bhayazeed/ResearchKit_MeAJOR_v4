import csv,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestMeAJOR(unittest.TestCase):
 def test_prepare_and_quality(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);src=d/'meajor.csv';o=d/'pilot.csv'
   rows=[]
   for i in range(14):
    label=i%2
    body=('This is an ordinary long example email with complete sentences and coherent office updates. '*15)+f' Document code {i}.'
    rows.append({'subject':f'Newsletter {i}','body':body,'label':str(float(label)),'source':'trec5' if i<7 else 'trec7','language':'en','sender':f'hash{i}'})
   with src.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   p=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_meajor.py'),'--input',str(src),'--output',str(o),'--per-class','3','--language-mode','supplied'],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr)
   with o.open(encoding='utf-8-sig') as f:chosen=list(csv.DictReader(f))
   self.assertEqual(len(chosen),6)
   self.assertEqual([x['dataset_label'] for x in chosen].count('1'),3)
   self.assertIn('meajor_sender',chosen[0]);self.assertTrue(all(x['meajor_body'] for x in chosen))
   c=subprocess.run([sys.executable,str(ROOT/'scripts/curate_meajor.py'),'--input',str(o),'--output-dir',str(d/'quality'),'--provider','langdetect','--policy','readability','--label','all'],capture_output=True,text=True)
   self.assertEqual(c.returncode,0,c.stderr)
   with (d/'quality/quality_audit.csv').open(encoding='utf-8-sig') as f:aud=list(csv.DictReader(f))
   self.assertEqual(len(aud),6);self.assertTrue(all(x['quality_accepted']=='1' for x in aud))
   second=subprocess.run([sys.executable,str(ROOT/'scripts/curate_meajor.py'),'--input',str(o),'--output-dir',str(d/'quality'),'--provider','langdetect','--policy','readability','--label','all'],capture_output=True,text=True)
   self.assertEqual(second.returncode,0,second.stderr)
   self.assertEqual(len((d/'quality/quality_checkpoint.jsonl').read_text().splitlines()),6)
 def test_binary_label(self):
  from phishbench.data import parse_gold
  self.assertEqual(parse_gold('1.0'),1);self.assertEqual(parse_gold('0.0'),0)
  with self.assertRaises(ValueError):parse_gold('')
if __name__=='__main__':unittest.main()
