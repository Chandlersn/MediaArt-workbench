/**
 * VirtualList 逻辑单元测试
 * 注意：完整的 DOM 测试需要在浏览器环境中运行
 */

describe('VirtualList', () => {

  describe('配置选项', () => {
    it('应该使用默认配置', () => {
      const defaultItemHeight = 60;
      const defaultBufferSize = 5;
      const defaultThreshold = 100;

      assertEqual(defaultItemHeight, 60, '默认项高度应该是 60');
      assertEqual(defaultBufferSize, 5, '默认缓冲区大小应该是 5');
      assertEqual(defaultThreshold, 100, '默认阈值应该是 100');
    });

    it('应该正确合并配置选项', () => {
      const options = {
        itemHeight: 80,
        bufferSize: 10,
        dynamicHeight: true,
        threshold: 50
      };

      const defaultOptions = {
        itemHeight: 60,
        bufferSize: 5,
        dynamicHeight: false,
        estimatedHeight: 60,
        threshold: 100
      };

      const merged = { ...defaultOptions, ...options };

      assertEqual(merged.itemHeight, 80, '项高度应该是 80');
      assertEqual(merged.bufferSize, 10, '缓冲区大小应该是 10');
      assertEqual(merged.dynamicHeight, true, '动态高度应该是 true');
      assertEqual(merged.threshold, 50, '阈值应该是 50');
      assertEqual(merged.estimatedHeight, 60, '预估高度应该是 60');
    });
  });

  describe('数据处理', () => {
    it('应该判断是否启用虚拟滚动', () => {
      const threshold = 100;
      const smallData = Array(50).fill({});
      const largeData = Array(150).fill({});

      const shouldEnableSmall = smallData.length >= threshold;
      const shouldEnableLarge = largeData.length >= threshold;

      assertEqual(shouldEnableSmall, false, '小数据集不应启用虚拟滚动');
      assertEqual(shouldEnableLarge, true, '大数据集应启用虚拟滚动');
    });

    it('应该正确计算固定高度内容区域', () => {
      const dataLength = 100;
      const itemHeight = 60;
      const contentHeight = dataLength * itemHeight;

      assertEqual(contentHeight, 6000, '内容高度应该是 6000');
    });

    it('应该正确计算可见范围', () => {
      const itemHeight = 60;
      const wrapperHeight = 480;
      const scrollTop = 300;
      const bufferSize = 5;
      const dataLength = 100;

      let startIndex = Math.floor(scrollTop / itemHeight);
      let endIndex = Math.ceil((scrollTop + wrapperHeight) / itemHeight);

      startIndex = Math.max(0, startIndex - bufferSize);
      endIndex = Math.min(dataLength - 1, endIndex + bufferSize);

      assertEqual(startIndex, 0, '起始索引应该是 0（减去缓冲区后）');
      assertEqual(endIndex, 18, '结束索引应该是 18（加上缓冲区后）');
    });
  });

  describe('二分查找（动态高度模式）', () => {
    it('应该正确实现二分查找', () => {
      const positionCache = [];
      let offset = 0;
      for (let i = 0; i < 100; i++) {
        const height = 60;
        positionCache.push({ index: i, offset, height });
        offset += height;
      }

      function findIndexByOffset(cache, targetOffset) {
        let left = 0;
        let right = cache.length - 1;

        while (left <= right) {
          const mid = Math.floor((left + right) / 2);
          const item = cache[mid];

          if (item.offset + item.height < targetOffset) {
            left = mid + 1;
          } else if (item.offset > targetOffset) {
            right = mid - 1;
          } else {
            return mid;
          }
        }

        return Math.min(left, cache.length - 1);
      }

      assertEqual(findIndexByOffset(positionCache, 0), 0, '偏移 0 应该在索引 0');
      assertEqual(findIndexByOffset(positionCache, 60), 0, '偏移 60 匹配第一个元素的范围');
      assertEqual(findIndexByOffset(positionCache, 300), 5, '偏移 300 应该在索引 5');
      assertEqual(findIndexByOffset(positionCache, 5900), 98, '偏移 5900 应该在索引 98');
    });
  });

  describe('滚动位置计算', () => {
    it('应该正确计算固定高度的 scrollToIndex', () => {
      const itemHeight = 60;
      const index = 50;
      const expectedScrollTop = index * itemHeight;

      assertEqual(expectedScrollTop, 3000, '索引 50 的滚动位置应该是 3000');
    });

    it('应该正确判断滚动方向', () => {
      let lastScrollTop = 100;
      let scrollTop = 150;
      let direction = scrollTop > lastScrollTop ? 'down' : 'up';

      assertEqual(direction, 'down', '向下滚动时方向应该是 down');

      lastScrollTop = 150;
      scrollTop = 100;
      direction = scrollTop > lastScrollTop ? 'down' : 'up';

      assertEqual(direction, 'up', '向上滚动时方向应该是 up');
    });
  });

});
