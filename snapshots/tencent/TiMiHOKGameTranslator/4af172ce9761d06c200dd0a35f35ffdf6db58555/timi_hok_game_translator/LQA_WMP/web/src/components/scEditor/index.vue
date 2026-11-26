<template>
  <div class="sceditor">
    <Editor
      :id="init.selector"
      v-model="contentValue"
      :init="init"
      :disabled="disabled"
      :placeholder="placeholder"
      @click="onClick"
    />
  </div>
</template>

<script>
import Editor from '@tinymce/tinymce-vue';
import tinymce from 'tinymce/tinymce';
import 'tinymce/themes/silver';
import 'tinymce/icons/default';
import 'tinymce/models/dom';
import { v4 as uuidv4 } from 'uuid';

// 引入编辑器插件
import 'tinymce/plugins/autoresize';  // 自动调整
import 'tinymce/plugins/code';  // 编辑源码
import 'tinymce/plugins/image';  // 插入编辑图片
import 'tinymce/plugins/media';  // 插入视频
import 'tinymce/plugins/link';  // 超链接
import 'tinymce/plugins/preview'; // 预览
import 'tinymce/plugins/table';  // 表格
import 'tinymce/plugins/pagebreak';  // 分页
import 'tinymce/plugins/lists';  // 列
import 'tinymce/plugins/advlist';  // 列
import 'tinymce/plugins/quickbars';  // 快速工具条
import 'tinymce/plugins/wordcount'; // 字数统计
import 'tinymce/plugins/searchreplace'; // 查询替换
import 'tinymce/plugins/visualblocks'; // 显示块
import 'tinymce/plugins/fullscreen'; // 全屏

const fontFamily = '\'PingFang SC\', \'Microsoft YaHei\', sans-serif';

export default {
  components: {
    Editor,
  },
  props: {
    modelValue: {
      type: String,
      default: '',
    },
    placeholder: {
      type: String,
      default: '',
    },
    height: {
      type: [Number, String],
      default: 300,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    plugins: {
      type: [String, Array],
      default:
				'code media link preview table quickbars pagebreak lists advlist \
					wordcount searchreplace visualblocks fullscreen autoresize',
    },
    toolbar: {
      type: [String, Array],
      default: 'undo redo |  forecolor backcolor bold italic underline strikethrough link | \
					blocks fontsize | alignleft aligncenter alignright alignjustify outdent indent | numlist bullist | \
					media table preview fullscreen | code selectall visualblocks | pagebreak searchreplace',
    },
    // 可添加默认模板
    // templates: {
    // 	type: Array,
    // 	default: () => []
    // },
    options: {
      type: Object,
      default: () => {
      },
    },
  },
  data() {
    const selector = `tinymce_${uuidv4()}`;
    return {
      editor: null,
      init: {
        selector,
        // external_plugins: {
        // 	sampleyo: "/tinymce/plugins/sample.js",
        // },
        // ui: {
        // 	useAutoToolbar: false
        // },
        language_url: 'https://cdn.jsdelivr.net/npm/tinymce-i18n@24.12.9/langs7/zh_CN.js',
        language: 'zh_CN',
        skin_url: 'https://cdn.jsdelivr.net/npm/tinymce@7.6.0/skins/ui/oxide',
        // skin_url: 'tinymce/skins/ui/tinymce-5', // 带边框
        content_css: false,
        removed_menuitems: 'fontfamily',
        menubar: true, // 最上方的菜单栏
        statusbar: true,
        plugins: this.plugins,
        toolbar: this.toolbar, // 底部的状态栏
        toolbar_mode: 'sliding',
        font_size_formats: '12px 14px 16px 18px 22px 24px 36px 72px',
        height: this.height,
        placeholder: this.placeholder,
        branding: false, // 去除水印
        resize: true,
        elementpath: true,
        content_style: `
        	* {
						font-size: 14px;
						font-family: ${fontFamily}
					}
					img {
						max-width: 100%;
					}
        `,
        // templates: this.templates,
        quickbars_selection_toolbar: 'forecolor backcolor bold italic underline strikethrough link',
        quickbars_image_toolbar: 'alignleft aligncenter alignright',
        quickbars_insert_toolbar: false,
        // file_picker_types: 'file image media',
        automatic_uploads: true, // 自动上传
        image_caption: false, // 不要标题
        image_advtab: true,
        convert_urls: false,
        // only insert
        table_use_colgroups: false,
        // 字体列表，不知道有没有用
        font_family_formats: fontFamily.replaceAll(',', ';').replaceAll('\'', ''),
        // table_sizing_mode: 'relative',
        // paste_auto_cleanup_on_paste: true,
        // paste_remove_styles: true,
        // paste_remove_styles_if_webkit: true,
        // paste_strip_class_attributes: true,
        async paste_postprocess(plugin, args) {
          // args.node可以获取到粘贴过来的所有dom节点，直接可以用操作dom的方式取修改它
          // 注意此函数不需要return返回值，直接修改即可
          // const tables = args.node.getElementsByTagName('table');
          // for (let i = 0; i < tables.length; i++) {
          // 	tables[i].setAttribute('width', '100%');
          // 	tables[i].style.width = '100%';
          // }
          // 兼容企微文档的表格图片
          const imageDom = args.node.getElementsByTagName('img');
          for (let i = 0; i < imageDom.length; i++) {
            const imageWidth = imageDom[i].getAttribute('width');
            // 设置外部粘贴图片的默认宽度
            if (!imageWidth) {
              imageDom[i].setAttribute('width', '1480');
            }
            // 查找父节点
            const { parentNode } = imageDom[i];
            //  获取父节点data-online-sheet-xxx属性调整img尺寸
            const sheetWidth = parentNode.getAttribute('data-online-sheet-width');
            if (sheetWidth) {
              imageDom[i].setAttribute('width', sheetWidth);
            }
            const sheetHeight = parentNode.getAttribute('data-online-sheet-height');
            if (sheetHeight) {
              imageDom[i].setAttribute('height', sheetHeight);
            }
          }

          // 表格删除 colgroup, outlook 兼容性有问题
          const colGroups = args.node.getElementsByTagName('colgroup');
          for (let i = 0; i < colGroups.length; i++) {
            colGroups[i].remove();
          }
          // 删除字体
          const fonts = args.node.getElementsByTagName('font');
          for (let i = 0; i < fonts.length; i++) {
            fonts[i].removeAttribute('face');
          }
          // 设置字体
          const handleTags = ['p', 'span', 'strong'];
          handleTags.forEach((tagName) => {
            const spans = args.node.getElementsByTagName(tagName);
            for (let i = 0; i < spans.length; i++) {
              spans[i].style.fontFamily = fontFamily;
            }
          });
        },
        // paste_as_text: true,
        // images_file_types: 'jpeg,jpg,jpe,jfi,jif,jfif,png,gif,bmp,webp',
        paste_data_images: false, // 禁止粘贴图像
        images_upload_handler: null, // 移除自定义上传处理函数
        // images_upload_handler(blobInfo) {
        //   return new Promise((resolve, reject) => {
        //     const data = new FormData();
        //     data.append('file', blobInfo.blob(), blobInfo.filename());
        //     data.append('file_type_id', 3);
        //     API.common.upload.post(data).then((res) => {
        //       resolve(process.env.VUE_APP_WEBPAGE + res);
        //     })
        //       .catch(() => {
        //         reject('Image upload failed');
        //       });
        //   });
        // },
        setup: (editor) => {
          // editor.on('init', function () {
          //   this.getBody().style.fontSize = '14px';
          //   this.getBody().style.fontFamily = fontFamily;
          // });
          this.editor = editor;
          editor.on('OpenWindow', (e) => {
            // FIX 编辑器在el-drawer中，编辑器的弹框无法获得焦点
            const D = document.querySelector('.el-drawer.open');
            const E = e.target.editorContainer;
            if (D && D.contains(E)) {
              const nowDA = document.activeElement;
              setTimeout(() => {
                document.activeElement.blur();
                nowDA.focus();
              }, 0);
            }
          });
        },
        ...this.options,
      },
      contentValue: this.modelValue,
    };
  },
  watch: {
    placeholder(val) {
      if (!this.contentValue) {
        this.editor && this.editor.getBody().setAttribute('data-mce-placeholder', val);
      }
    },
    modelValue(val) {
      this.contentValue = val || '';
    },
    contentValue(val) {
      this.$emit('update:modelValue', val);
    },
  },
  // mounted() {
  //   tinymce.init({});
  //   // console.log(this.init.selector)
  //   // console.log(tinymce)
  // },
  methods: {
    onClick(e) {
      // 没啥用感觉
      this.$emit('onClick', e, tinymce);
    },
    // 获取内容
    getContent(args = {}) {
      // args (Object)  Optional content object, this gets passed around through the whole get process.
      // 以纯文本的形式获取当前激活的编辑器内容 ↓
      // tinymce.activeEditor.getContent({ format: 'text' });
      return tinymce.get(this.init.selector).getContent(args);
    },
  },
};
</script>

<style>
/* 不显示 Upgrade */
.tox-promotion {
  display: none;
}
</style>
