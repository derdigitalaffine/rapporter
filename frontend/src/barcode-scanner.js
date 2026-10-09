export const nativeBarcodeFormats={
 code_128:'code128',ean_13:'ean13',ean_8:'ean8',upc_a:'upca',upc_e:'upce',code_39:'code39',itf:'itf',
 qr_code:'qrcode',data_matrix:'datamatrix',pdf417:'pdf417',aztec:'aztec',
};

export const requiredOneDimensionalNativeFormats=['ean_13','ean_8','upc_a','upc_e','code_128','code_39','itf'];

export function nativeScannerPlan(supported=[]){
 const accepted=supported.filter(item=>nativeBarcodeFormats[item]);
 const oneDimensionalComplete=requiredOneDimensionalNativeFormats.every(item=>accepted.includes(item));
 return {accepted,oneDimensionalComplete,useFallback:!oneDimensionalComplete};
}
