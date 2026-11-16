from PIL import Image
def cases():
 q={'color':{'type':'choice','instructions':'Which color is named?','criteria':{'red':'Red','blue':'Blue'}},'yesno':{'type':'noul','instructions':'Is the named color red?'},'redness':{'type':'score','instructions':'How clearly does the text identify the color as red?','criteria':['Not red','Possibly red','Clearly red']}}
 blue=Image.new('RGB',(256,256),'blue');red=Image.new('RGB',(256,256),'red')
 vq={'which':{'type':'choice','instructions':'Which image is red?','criteria':{'first':'The first image','second':'The second image'}}}
 cases=[('text_readme','The color is red. ',q,[]),('json_state',{'color':'red'}, {'q':q['color']},[]),('reverse_options','The color is red. ',{'q':dict(q['color'],criteria={'blue':'Blue','red':'Red'})},[]),('noul_reverse','The color is red. ',{'q':{'type':'noul','instructions':'Is the color red?','criteria':{'false':'No','true':'Yes'}}},[]),('two_images',{},vq,[blue,red]),('two_images_explicit','<image>\n<image>\n',vq,[blue,red]),('two_images_reversed',{},vq,[red,blue]),('one_image',{}, {'q':{'type':'choice','instructions':'What color is the image?','criteria':{'blue':'Blue','red':'Red'}}},[red]),('256_options','The number is 255. ',{'q':{'type':'choice','instructions':'Which number is named?','criteria':{str(i):str(i) for i in range(256)}}},[])]
 return cases
