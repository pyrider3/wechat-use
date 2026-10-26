"""Private local OCR worker. Receives PNG bytes only; no desktop actions or network images."""
import base64,contextlib,io,json,sys
from PIL import Image
import numpy as np
from rapidocr import RapidOCR
with contextlib.redirect_stdout(sys.stderr):
 engine=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1})
for line in sys.stdin:
 request={}
 try:
  request=json.loads(line);im=Image.open(io.BytesIO(base64.b64decode(request['png']))).convert('RGB')
  with contextlib.redirect_stdout(sys.stderr):result=engine(np.asarray(im)[:,:,::-1].copy())
  rows=[]
  if result.txts is not None:
   for text,confidence,box in zip(result.txts,result.scores,result.boxes):
    xs=[float(p[0]) for p in box];ys=[float(p[1]) for p in box]
    rows.append({'text':text,'confidence':float(confidence),'bounds':[min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]})
  print(json.dumps({'id':request.get('id'),'rows':rows},ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({'id':request.get('id'),'error':str(e)}),flush=True)
