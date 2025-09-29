#!\bin\bash
echo 'save orig data'
#rm oirg/* -r
#mkdir orig

#mv ../table-transformer/src/models/paddleocr_models/det orig/det -v
#mv ../table-transformer/src/models/paddleocr_models/rec orig/rec -v
#cp orig/det ../table-transformer/src/models/paddleocr_models/det.old -v
#cp orig/rec ../table-transformer/src/models/paddleocr_models/rec.old -v

echo 'extracting data'
mkdir ../table-transformer/src/models/paddleocr_models/det
tar  --strip-components=1 -xfen_PP-OCRv3_det_infer.tar -C ../table-transformer/src/models/paddleocr_models/det

mkdir ../table-transformer/src/models/paddleocr_models/rec
tar --strip-components=1 -xf en_PP-OCRv3_rec_infer.tar -C ../table-transformer/src/models/paddleocr_models/rec

echo 'copying yaml files'
cp ch_PP-OCRv3_det_cml.yml ../table-transformer/src/models/paddleocr_models/det/inference.yml -v
cp en_PP-OCRv3_rec.yml ../table-transformer/src/models/paddleocr_models/rec/inference.yml -v




