<!--
 * @Description: 画图
-->
<template>
  <el-drawer title="数据审核" size="100%" v-model="visible" destroy-on-close @close="filterNegative = true">
    <!-- 标题 -->
    <template #header>
      <div class="flex justify-between">
        <div class="flex items-center">
          <div class="font-bold">数据审核</div>
          <el-divider direction="vertical" class="!mx-3 !vertical-middle" />

          <!-- 操作提示 -->
          <div class="flex items-center opacity-85">
            可操作
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">白色图像框</el-tag>， 上方有
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">放大预览</el-tag>，
            鼠标移到白色边框会显示
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">可选</el-tag>， 选中即可按
            <el-tag size="small" type="info" class="ml-1.5 mr-0.25 !text-black opacity-75 !py-2.5">Delete</el-tag>
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">Backspace</el-tag>
            进行删除，选中虚线框可
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">回滚删除</el-tag>
            ，点击右下方的
            <el-tag size="small" type="info" class="mx-1.5 !text-black opacity-75 !py-2.5">确认</el-tag>
            按钮即可保存
          </div>
        </div>

        <div class="flex items-center">
          <div class="flex items-center mr-12 opacity-90">
            <div class="text-sm">隐藏系统标记冗余：</div>
            <el-switch size="small" :disabled="loading" v-model="filterNegative" @change="open(dataId, imgUrl)" />
          </div>
        </div>
      </div>
    </template>

    <div class="relative flex items-center h-full px-[30px] img-draw-body" v-loading="loading">
      <!-- 上一个 -->
      <el-button
        v-if="hasPrev"
        v-loading="loading"
        icon="ArrowLeft"
        class="el-carousel__arrow absolute top-1/2 left-[-9px] -translate-y-1/2 z-9999 !text-white"
        @click="open(pageReviews[currentIndex - 1].id, pageReviews[currentIndex - 1].revert_img_path)"
      />

      <!-- 左侧 -->
      <div class="relative h-full" style="width: calc(50% - 70px)">
        <!-- 标题 -->
        <div
          v-if="imgPositionSize.left"
          class="absolute leading-6"
          :style="{
            top: `${imgPositionSize.left.py - 34}px`,
            left: `${imgPositionSize.left.px}px`,
          }"
        >
          <div class="flex items-center">
            <div class="w-1 bg-blue rounded-1 mr-2 h-full text-blue">|</div>
            <div class="font-bold">操作区</div>
            <el-divider direction="vertical" class="!ml-2.75 !mr-2.75 !my-auto !vertical-middle" />
            <div class="opacity-75 text-sm">还原上报数据</div>
          </div>
        </div>
        <!-- 图像 -->
        <canvas ref="leftImgCanvas" :width="canvasSize.width" :height="canvasSize.height" />
        <!-- 框 -->
        <canvas
          class="absolute top-0 left-0"
          ref="leftRectCanvas"
          :width="canvasSize.width"
          :height="canvasSize.height"
        />
      </div>

      <!-- 中间 -->
      <div class="flex flex-col h-full justify-center">
        <el-divider class="!mx-20 !h-[10%] opacity-75" direction="vertical" />

        <div class="text-center my-2 opacity-60 leading-6.75">
          <!-- ID -->
          <div>ID: {{ dataId }}</div>

          <!-- 人工标记冗余 -->
          <div class="flex justify-center">
            <div>人工标记冗余：</div>
            <div class="w-6">{{ dirtyNum.user }}</div>
            <div>个</div>
          </div>

          <!-- 系统标记冗余 -->
          <div class="flex justify-center">
            <div>系统标记冗余：</div>
            <div class="w-6">{{ dirtyNum.system + negativeNum }}</div>
            <div>个</div>
          </div>
        </div>
        <el-divider class="!mx-20 !h-[10%] opacity-75" direction="vertical" />
      </div>

      <!-- 右侧 -->
      <div class="relative" style="width: calc(50% - 70px)">
        <!-- 标题 -->
        <div
          v-if="imgPositionSize.right"
          class="absolute flex items-center leading-6"
          :style="{
            top: `${imgPositionSize.right.py - 34}px`,
            left: `${imgPositionSize.right.px}px`,
          }"
        >
          <div class="w-1 bg-blue rounded-1 mr-2 text-blue">|</div>
          <div class="font-bold">预览区</div>
          <el-divider direction="vertical" class="!ml-2.75 !mr-2.75 !my-auto !vertical-middle" />
          <div class="opacity-75 text-sm">标记审核数据</div>
        </div>
        <!-- 图像 -->
        <canvas ref="rightImgCanvas" :width="canvasSize.width" :height="canvasSize.height" />
        <!-- 框 -->
        <canvas
          class="absolute top-0 left-0"
          ref="rightRectCanvas"
          :width="canvasSize.width"
          :height="canvasSize.height"
        />
      </div>

      <!-- 下一个 -->
      <el-button
        v-if="hasNext"
        v-loading="loading"
        icon="ArrowRight"
        class="el-carousel__arrow absolute right-[-9px] top-1/2 -translate-y-1/2 z-9999 !text-white"
        @click="open(pageReviews[currentIndex + 1].id, pageReviews[currentIndex + 1].revert_img_path)"
      />

      <!-- 预览 -->
      <div class="absolute left-1/2 -translate-x-1/2 top-0 z-99">
        <div
          class="relative overflow-hidden"
          style="border-radius: 50%"
          :style="{ width: scaleCircleWidth, height: scaleCircleWidth }"
        >
          <!-- 图像 -->
          <canvas
            class="absolute z-0"
            :style="{
              top: `calc(-${mouseY * previewScale}px + (${scaleCircleWidth} / 2))`,
              left: `calc(-${mouseX * previewScale}px + (${scaleCircleWidth} / 2))`,
            }"
            ref="previewImgCanvas"
            :width="canvasSize.width * previewScale"
            :height="canvasSize.height * previewScale"
          />
          <!-- 框 -->
          <canvas
            class="absolute z-1"
            ref="previewRectCanvas"
            :style="{
              top: `calc(-${mouseY * previewScale}px + (${scaleCircleWidth} / 2))`,
              left: `calc(-${mouseX * previewScale}px + (${scaleCircleWidth} / 2))`,
            }"
            :width="canvasSize.width * previewScale"
            :height="canvasSize.height * previewScale"
          />
          <!-- 瞄准 -->
          <img
            class="absolute z-2"
            style="filter: invert(100%)"
            :src="aim"
            alt="瞄准"
            :style="{ width: scaleCircleWidth, height: scaleCircleWidth }"
          />
        </div>

        <!-- 是否可选 -->
        <div v-show="isSelectable" class="mt-4 flex justify-center opacity-80">
          <div class="bg-black text-white py-1.25 px-1.75 text-[14px] rounded-1">可选</div>
        </div>
      </div>
    </div>

    <!-- 底部 -->
    <template #footer>
      <div class="w-full" style="flex: auto">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :disabled="!filterNegative" @click="confirm">确认</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script>
import { xor, remove, cloneDeep } from 'lodash-es';
import { customRequest } from '@/utils/service.ts';
import aim from '@/assets/layouts/aim.png?url';

const emptyRect = { img: [], text: [] };

export default {
  name: 'imgDraw',
  props: {
    pageReviews: {
      type: Array,
      default: () => [],
    },
  },
  data() {
    return {
      aim,
      loading: false,
      useId: 0,
      dataId: 0,
      imgUrl: '',
      mouseX: 0,
      mouseY: 0,
      projectId: this.$route.meta.value,
      visible: false,
      filterNegative: true, // 过滤负数
      canvas2dCtx: {
        left: null,
        right: null,
        preview: null,
      },
      canvasSize: {
        width: 100,
        height: 100,
      },
      imgPositionSize: {
        left: null,
        right: null,
        preview: null,
      },

      originalRect: cloneDeep(emptyRect),
      rect: cloneDeep(emptyRect),
      realRect: {
        left: null,
        right: null,
        preview: null,
      },
      rectColor: {
        text: 'rgb(255, 0, 0)',
        img: 'rgb(255, 255, 255)',
      },
      lineWidth: 2,
      selectableWidth: 4,
      rectPointWidth: 3,
      selectKeys: [],

      // 删除相关
      dirtyNum: { user: 0, system: 0 },
      originalDirtyText: [],
      originImgDirtyTag: {},
      deleteKeys: cloneDeep(emptyRect),
      negativeKeys: cloneDeep(emptyRect),
      systemDirtyKeys: [],

      scaleCircleWidth: '8vw',
      previewScale: 4,
      isSelectable: false,
    };
  },
  async created() {
    this.canvasSize.height = window.innerHeight - 176;
    this.canvasSize.width = window.innerWidth / 2 - 130;
  },
  // async mounted() {
  //   await this.loadData();
  //   await this.$nextTick();
  //   this.loadCanvas('left');
  //   this.loadCanvas('right');
  //   document.addEventListener('keydown', this.onDelete);
  // },
  watch: {
    'deleteKeys.img'(val) {
      const dirtyNum = { user: 0, system: 0 };
      val.forEach((key) => {
        const tag = this.originImgDirtyTag[key] || 'user';
        dirtyNum[tag] += 1;
      });
      dirtyNum.system += this.originalDirtyText.filter(item => item.tag === 'system').length;
      this.dirtyNum = dirtyNum;
    },
  },
  computed: {
    /** 负值框数量 */
    negativeNum() {
      let num = 0;
      Object.values(this.negativeKeys).forEach(values => (num += values.length));
      return num;
    },
    /** 当前是第几条可审核数据 */
    currentIndex() {
      return this.pageReviews.findIndex(item => item.id === this.dataId);
    },
    /** 有上一个 */
    hasPrev() {
      return this.currentIndex > 0;
    },
    /** 有下一个 */
    hasNext() {
      return this.currentIndex !== this.pageReviews.length - 1 && this.currentIndex !== -1;
    },
  },
  unmounted() {
    // 清除删除监听
    document.removeEventListener('keydown', this.onDelete);
  },
  methods: {
    async open(dataId, url) {
      document.removeEventListener('keydown', this.onDelete);
      this.loading = true;
      // 重新初始化值
      this.rect = cloneDeep(emptyRect);
      this.selectKeys = [];
      this.deleteKeys = cloneDeep(emptyRect);
      this.isSelectable = false;

      this.visible = true;
      this.imgUrl = url;
      await this.loadData(dataId);
      await this.$nextTick();
      this.loadCanvas('left', url);
      this.loadCanvas('right', url);
      this.loadCanvas('preview', url);
      document.addEventListener('keydown', this.onDelete);
    },
    /** 获取并处理边框数据 */
    async loadData(dataId) {
      // 初始化数据
      this.originImgDirtyTag = {};
      this.originalDirtyText = [];

      this.dataId = dataId;
      const { data } = await customRequest({
        url: '/api/image/data_review',
        params: {
          project_id: this.projectId,
          data_id: dataId,
        },
      }).finally(() => {
        setTimeout(() => {
          this.loading = false;
        }, 50);
      });
      try {
        this.useId = data.data_review.id;
        // 删除数据
        const deletedRect = JSON.parse(data.data_review.dirty_rect_location);
        const originImgDirtyTag = {};
        (deletedRect.image || []).forEach((item) => {
          originImgDirtyTag[item.key] = item.tag;
        });
        this.originImgDirtyTag = originImgDirtyTag;
        this.originalDirtyText = deletedRect.text || [];
        this.systemDirtyKeys = [
          ...this.originalDirtyText.filter(item => item.tag === 'system').map(item => item.key),
          ...(deletedRect.image || []).filter(item => item.tag === 'system').map(item => item.key),
        ];
        this.deleteKeys.img = (deletedRect.image || []).map(item => item.key);
        this.deleteKeys.text = (deletedRect.text || []).map(item => item.key);

        // 原始数据
        const rect = data.data_review.rect_location;
        this.originalRect = cloneDeep(rect);
        rect.img = rect.image;
        const rectKeys = ['text', 'img'];
        this.negativeKeys = cloneDeep(emptyRect);
        rectKeys.forEach((key) => {
          this.rect[key] = rect[key].map(item => ({
            key: item.key,
            data: { x: item.corners[0], y: item.corners[1], w: item.corners[2], h: item.corners[3] },
          }));

          const originalRect = cloneDeep(this.rect[key]);
          this.rect[key] = this.rect[key]
            .filter(item => !this.systemDirtyKeys.includes(item.key))
            .filter((item) => {
              if (item.data.x >= 0 && item.data.y >= 0 && item.data.w >= 0 && item.data.h >= 0) {
                return true;
              }
              this.negativeKeys[key].push(item.key);
              return false;
            });

          if (!this.filterNegative) {
            this.rect[key] = originalRect;
          }
        });
      } catch (e) {
        console.warn(e);
      }
    },
    /** 加载 */
    loadCanvas(side, url) {
      console.log('=>(imgDraw.vue:402) url', url);
      const canvas = this.$refs[`${side}ImgCanvas`];
      const w = canvas.width;
      const h = canvas.height;
      if (canvas.getContext) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(
          0,
          0,
          side === 'preview' ? this.canvasSize.width * this.previewScale : this.canvasSize.width,
          side === 'preview' ? this.canvasSize.height * this.previewScale : this.canvasSize.height,
        );
        this.canvas2dCtx[side] = this.$refs[`${side}RectCanvas`].getContext('2d');
        const img = new Image();
        // img.src = 'http://localhost:3333/api-pro/LocalPlatform/projectFolder/1/jobFolder/495/images_folder/495-132-LAN_ID_ID.png'; // 图片地址示例
        img.src = `${import.meta.env.VITE_RESOURCE_API}${url}`; // 图片地址示例
        // eslint-disable-next-line @typescript-eslint/no-this-alias
        const that = this;
        img.onload = function () {
          const iw = this.width;
          const ih = this.height;
          let scaleIw = iw;
          let scaleIh = ih;

          if (side === 'preview') {
            /* 预览放大 */
            scaleIw = iw * that.previewScale;
            scaleIh = ih * that.previewScale;
          }

          const local = that.calculate(w, h, scaleIw, scaleIh);

          // that.canvas2dCtx[side].fillStyle = 'white';
          // that.canvas2dCtx[side].fill();
          ctx.drawImage(this, local.px, local.py, local.calcPw, local.calcPh);
          that.imgPositionSize[side] = { ...local, ratio: local.calcPw / iw };
          that.realRect[side] = cloneDeep(that.rect);
          const rectKeys = ['img', 'text'];
          rectKeys.forEach((key) => {
            that.realRect[side][key] = that.rect[key].map(item => ({
              key: item.key,
              data: that.translatePositionSize(item.data, side),
            }));
          });

          if (side === 'left') {
            /* 左 */
            // that.drawRectLine();
            that.drawOperableRect('left');
            // 鼠标事件监听
            that.leftCanvasListener();
          } else if (side === 'right') {
            /* 右 */
            that.drawRightRect();
          } else if (side === 'preview') {
            /* 预览 */
            that.drawOperableRect('preview');
          }
        };
      }
    },
    /** 左图 / 预览区域 - 根据数据画框 */
    drawOperableRect(side) {
      this.canvas2dCtx[side].clearRect(
        0,
        0,
        side === 'preview' ? this.canvasSize.width * this.previewScale : this.canvasSize.width,
        side === 'preview' ? this.canvasSize.height * this.previewScale : this.canvasSize.height,
      );

      // 文本框
      this.realRect[side].text.forEach((rect) => {
        if (this.deleteKeys.text.includes(rect.key) || this.negativeKeys.text.includes(rect.key)) {
          this.drawRectDash(this.canvas2dCtx[side], rect.data, 'text');
        } else {
          this.drawRectLine(this.canvas2dCtx[side], rect.data, 'text');
        }
      });

      // 图像框
      this.realRect[side].img.forEach((rect) => {
        if (this.deleteKeys.img.includes(rect.key) || this.negativeKeys.img.includes(rect.key)) {
          this.drawRectDash(this.canvas2dCtx[side], rect.data);
        } else if (this.selectKeys.includes(rect.key)) {
          this.drawRectSelectedLine(this.canvas2dCtx[side], rect.data);
        } else {
          this.drawRectLine(this.canvas2dCtx[side], rect.data);
        }
      });
    },
    /** 右图 - 根据数据画框 */
    drawRightRect() {
      this.canvas2dCtx.right.clearRect(0, 0, this.canvasSize.width, this.canvasSize.height);

      // 文本框
      this.realRect.right.text.forEach((rect) => {
        if (!this.deleteKeys.text.includes(rect.key) && !this.negativeKeys.text.includes(rect.key)) {
          this.drawRectLine(this.canvas2dCtx.right, rect.data, 'text');
        }
      });

      // 图像框
      this.realRect.right.img.forEach((rect) => {
        if (!this.deleteKeys.img.includes(rect.key) && !this.negativeKeys.img.includes(rect.key)) {
          this.drawRectLine(this.canvas2dCtx.right, rect.data);
        }
      });
    },
    /** 计算出图片画在canvas中的四个参数 */
    calculate(w, h, pw, ph) {
      let px = 0;
      let py = 0;
      let calcPh = ph;
      let calcPw = pw;
      if (calcPw < w && calcPh < h) {
        // 图片尺寸小于 canvas
        px = 0.5 * w - 0.5 * calcPw;
        py = 0.5 * h - 0.5 * calcPh;
        console.log('图片尺寸小于 canvas');
      } else if (calcPh / calcPw > h / w) {
        // 图片高大于 canvas
        const uu = calcPh;
        calcPh = h;
        calcPw = (calcPw * h) / uu;
        px = 0.5 * w - 0.5 * calcPw;
        console.log('图片高大于 canvas');
      } else {
        // 图片宽大于等于 canvas
        const uu = calcPw;
        calcPw = w;
        calcPh = (calcPh * calcPw) / uu;
        py = 0.5 * h - 0.5 * calcPh;
        console.log('图片宽大于等于 canvas');
      }
      return { px, py, calcPw, calcPh };
    },
    /** 位置尺寸换算 */
    translatePositionSize(rect, side) {
      const refer = this.imgPositionSize[side];
      if (rect.x < 0) {
        console.log('=>(imgDraw.vue:223) rect.x', rect.x);
      }
      if (rect.y < 0) {
        console.log('=>(imgDraw.vue:223) rect.y', rect.y);
      }
      return {
        x: rect.x * refer.ratio + refer.px,
        y: rect.y * refer.ratio + refer.py,
        w: rect.w * refer.ratio,
        h: rect.h * refer.ratio,
      };
    },
    /** 画实线框 */
    drawRectLine(ctx, rect, type = 'img', w = this.lineWidth) {
      ctx.beginPath();
      ctx.strokeStyle = this.rectColor[type];
      ctx.globalAlpha = 1;
      ctx.lineWidth = w;
      ctx.setLineDash([]);
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      ctx.closePath();
    },
    /** 选中实线框 - 圆点 */
    // drawRectSelectedLine(rect, type = 'text') {
    //   this.drawRectLine(rect, type);
    //
    //   const pointList = [];
    //   pointList.push({ x: rect.x, y: rect.y }); // 左上角
    //   pointList.push({ x: rect.x + rect.w / 2, y: rect.y }); // 中上
    //   pointList.push({ x: rect.x + rect.w, y: rect.y }); // 右上角
    //   pointList.push({ x: rect.x + rect.w, y: rect.y + rect.h / 2 }); // 右中
    //   pointList.push({ x: rect.x + rect.w, y: rect.y + rect.h }); // 右下角
    //   pointList.push({ x: rect.x + rect.w / 2, y: rect.y + rect.h }); // 中下
    //   pointList.push({ x: rect.x, y: rect.y + rect.h }); // 左下角
    //   pointList.push({ x: rect.x, y: rect.y + rect.h / 2 }); // 左中
    //
    //   // 开始画点
    //   pointList.forEach((item) => {
    //     this.canvas2dCtx.left.beginPath();
    //     this.canvas2dCtx.left.arc(item.x, item.y, this.circleRadius, 0, 2 * Math.PI);
    //     this.canvas2dCtx.left.fillStyle = this.rectColor[type];
    //     this.canvas2dCtx.left.fill();
    //     this.canvas2dCtx.left.strokeStyle = this.rectColor[type];
    //     this.canvas2dCtx.left.lineWidth = this.lineWidth;
    //     this.canvas2dCtx.left.globalAlpha = 1;
    //     this.canvas2dCtx.left.stroke();
    //     this.canvas2dCtx.left.closePath();
    //   });
    // },
    /** 选中实线框 - 方块 */
    drawRectSelectedLine(ctx, rect, type = 'img') {
      this.drawRectLine(ctx, rect, type);

      const rectList = [];
      rectList.push({ x: rect.x, y: rect.y }); // 左上角
      rectList.push({ x: rect.x + rect.w / 2, y: rect.y }); // 中上
      rectList.push({ x: rect.x + rect.w, y: rect.y }); // 右上角
      rectList.push({ x: rect.x + rect.w, y: rect.y + rect.h / 2 }); // 右中
      rectList.push({ x: rect.x + rect.w, y: rect.y + rect.h }); // 右下角
      rectList.push({ x: rect.x + rect.w / 2, y: rect.y + rect.h }); // 中下
      rectList.push({ x: rect.x, y: rect.y + rect.h }); // 左下角
      rectList.push({ x: rect.x, y: rect.y + rect.h / 2 }); // 左中
      const subW = this.rectPointWidth / 2;
      rectList.forEach((item) => {
        /* eslint-disable */
        item.x = item.x - subW;
        item.y = item.y - subW;
        item.w = this.rectPointWidth;
        item.h = this.rectPointWidth;
        /* eslint-enable */
      });

      // 开始画点
      rectList.forEach((item) => {
        this.drawRectLine(ctx, item, type, this.rectPointWidth);
      });
    },
    /** 画虚线框 - 代表已删除 */
    drawRectDash(ctx, rect, type = 'img') {
      ctx.beginPath();
      ctx.strokeStyle = this.rectColor[type];
      ctx.globalAlpha = 1;
      ctx.lineWidth = this.lineWidth;
      ctx.setLineDash([5, 2.5]); // 设置虚线样式
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      ctx.closePath();
    },
    /** 判断是不是在边框上，为了方便选中，可选区域会扩大 */
    isInRectBorder(e, type) {
      this.mouseX = e.clientX - this.$refs.leftRectCanvas.getBoundingClientRect().left;
      this.mouseY = e.clientY - this.$refs.leftRectCanvas.getBoundingClientRect().top;
      // 判断鼠标点击是否在边框上
      // 大的减小的，可以得知是不是点击的边框
      for (let i = 0; i < this.realRect.left[type].length; i++) {
        const item = this.realRect.left[type][i];
        const itemData = item.data;
        const outerBorderRange = {
          left: itemData.x - this.selectableWidth / 2,
          top: itemData.y - this.selectableWidth / 2,
          right: itemData.x + itemData.w + this.selectableWidth / 2,
          bottom: itemData.y + itemData.h + this.selectableWidth / 2,
        };
        const innerBorderRange = {
          left: itemData.x + this.selectableWidth / 2,
          top: itemData.y + this.selectableWidth / 2,
          right: itemData.x + itemData.w - this.selectableWidth / 2,
          bottom: itemData.y + itemData.h - this.selectableWidth / 2,
        };
        const outerFlag =          this.mouseX >= outerBorderRange.left
          && this.mouseX <= outerBorderRange.right
          && this.mouseY >= outerBorderRange.top
          && this.mouseY <= outerBorderRange.bottom;
        const innerFlag =          this.mouseX >= innerBorderRange.left
          && this.mouseX <= innerBorderRange.right
          && this.mouseY >= innerBorderRange.top
          && this.mouseY <= innerBorderRange.bottom;
        if (outerFlag && !innerFlag) {
          this.isSelectable = true;
          return item.key;
        }
        this.isSelectable = false;
      }
    },
    /** 事件监听 */
    leftCanvasListener() {
      /* 点击事件 */
      this.$refs.leftRectCanvas.onclick = (e) => {
        const imgRectKey = this.isInRectBorder(e, 'img');
        if (imgRectKey) {
          if (this.deleteKeys.img.includes(imgRectKey)) {
            // 删除框选中恢复
            remove(this.deleteKeys.img, key => key === imgRectKey);
            this.deleteKeys.img = [...this.deleteKeys.img];
            this.drawRightRect();
          } else {
            // 选中态和常规态切换
            this.selectKeys = xor(this.selectKeys, [imgRectKey]);
          }
          console.log('点击在边框上');
          this.drawOperableRect('left');
          this.drawOperableRect('preview');
        } else {
          console.log('点击不在边框上');
        }
      };

      /* 鼠标移动事件 */
      this.$refs.leftRectCanvas.onmousemove = (e) => {
        const textRectKey = this.isInRectBorder(e, 'text');
        const imgRectKey = this.isInRectBorder(e, 'img');

        // 赋予不同的鼠标光标样式
        if (imgRectKey) {
          // 图像框可选中
          this.$refs.leftRectCanvas.style.cursor = 'pointer';
        } else if (textRectKey) {
          // 文本框不可选中
          this.$refs.leftRectCanvas.style.cursor = 'not-allowed';
        } else {
          this.$refs.leftRectCanvas.style.cursor = 'default';
        }
      };
    },
    /** 删除监听 */
    onDelete(event) {
      if (event.key === 'Delete') {
        console.log('Delete 键被按下');
        this.applyDeleteRect();
      } else if (event.key === 'Backspace') {
        console.log('Backspace 键被按下');
        this.applyDeleteRect();
      }
    },
    /** 执行删框操作 */
    applyDeleteRect() {
      this.deleteKeys.img = xor(this.deleteKeys.img, this.selectKeys);
      this.selectKeys = [];
      this.drawOperableRect('left');
      this.drawRightRect();
      this.drawOperableRect('preview');
    },
    /** 确认保存 */
    async confirm() {
      const emptyResultRect = { text: [], image: [] };
      // 确认要的
      const checkRect = cloneDeep(emptyResultRect);
      checkRect.text = (this.rect.text || []).map(item => ({
        key: item.key,
        corners: [item.data.x, item.data.y, item.data.w, item.data.h],
      }));
      checkRect.image = (this.rect.img || [])
        .filter(item => !this.deleteKeys.img.includes(item.key))
        .map(item => ({
          key: item.key,
          corners: [item.data.x, item.data.y, item.data.w, item.data.h],
        }));

      // 删除的
      const deleteRect = cloneDeep(emptyResultRect);
      deleteRect.image = [
        ...(this.rect.img || [])
          .filter(item => this.deleteKeys.img.includes(item.key))
          .map(item => ({
            key: item.key,
            corners: [item.data.x, item.data.y, item.data.w, item.data.h],
            tag: this.originImgDirtyTag[item.key] || 'user',
          })),
        ...(this.originalRect.image || [])
          .filter(item => this.negativeKeys.img.includes(item.key))
          .map(item => ({ ...item, tag: 'system' })),
      ];
      deleteRect.text = [
        ...(this.originalDirtyText || []),
        ...(this.originalRect.text || [])
          .filter(item => this.negativeKeys.text.includes(item.key))
          .map(item => ({ ...item, tag: 'system' })),
      ];

      await customRequest({
        url: '/api/image/data_review',
        method: 'patch',
        data: {
          id: this.useId,
          project_id: this.projectId,
          check_rect_location: JSON.stringify(checkRect),
          dirty_rect_location: JSON.stringify(deleteRect),
        },
      });
      this.$message.success('修改成功');
      this.visible = false;
    },
  },
};
</script>

<style>
.el-carousel__arrow {
  --el-carousel-arrow-font-size: 12px;
  --el-carousel-arrow-size: 36px;
  --el-carousel-arrow-background: rgba(31, 45, 61, 0.33);
  --el-carousel-arrow-hover-background: rgba(31, 45, 61, 0.4);
  --el-carousel-indicator-width: 30px;
  --el-carousel-indicator-height: 2px;
  --el-carousel-indicator-padding-horizontal: 4px;
  --el-carousel-indicator-padding-vertical: 12px;
  --el-carousel-indicator-out-color: var(--el-border-color-hover);
}

/* 数据审核抽屉 body 禁止出现滚动条，避免切换开关时内容宽度抖动 */
.el-drawer:has(.img-draw-body) .el-drawer__body {
  overflow: hidden;
}
.img-draw-body {
  overflow: hidden;
}
</style>
